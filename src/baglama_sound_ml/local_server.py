"""Loopback-only recording library and feedback service; no cloud dependencies."""
from __future__ import annotations
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import urlsplit, parse_qs, unquote
import base64
import hashlib
import io
import json
import math
import secrets
import socket
import threading
import wave
import zipfile
import numpy as np
from .audio import RATE, finish, validate_request
from .capture_catalog import catalog, validate_label
from .continuation import compare_continuations
from .feedback_store import FeedbackStore
from .final_tone import detect_final_tone, synthetic_strum
from .final_tone_cases import FinalToneCases
from .local_library import LocalLibrary
from .neural import load_model
from .synthesis import neural, sample


def wav_bytes(audio: np.ndarray, rate: int, normalize: bool = False) -> bytes:
    if normalize and np.max(np.abs(audio))>1e-8:
        audio=finish(audio,rate)
    data=io.BytesIO()
    with wave.open(data,'wb') as stream:
        stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(rate)
        stream.writeframes(np.round(np.clip(audio,-1,1)*32767).astype('<i2').tobytes())
    return data.getvalue()


class LabApplication:
    def __init__(self, project: Path, library: Path, model: Path, dataset: Path | None = None):
        self.project=project.resolve()
        self.dataset=(dataset or self.project/'data/recordings').resolve()
        self.library=LocalLibrary(library)
        self.feedback=FeedbackStore(self.library)
        self.final_tone_cases=FinalToneCases(self.library.root/'final-tone-tests')
        self.model=model.resolve()
        self.token=secrets.token_urlsafe(32)
        self.usage={}
        if self.model.exists():
            _,metadata=load_model(self.model)
            for kind in ('training','validation'):
                for identity in metadata.get(kind+'_identities',[]):
                    self.usage[identity]=kind
        self.model_id=hashlib.sha256(self.model.read_bytes()).hexdigest() if self.model.exists() else None
        self.project_id=hashlib.sha256(str(self.project).encode()).hexdigest()[:16]

    def config(self) -> dict:
        return dict(service='BaglamaSoundML',projectId=self.project_id,token=self.token,
                    catalog=catalog(),modelId=self.model_id,modelReady=self.model.exists(),
                    recordingLimitSeconds=10,localOnly=True)

    def samples(self, trash: bool = False) -> list[dict]:
        rows=self.library.samples(trash)
        for row in rows:
            row['modelUsage']=self.usage.get(row['identity'],'unseen')
        return rows

    def add_recording(self, body: dict) -> dict:
        if body.get('confirmedReal') is not True:
            raise ValueError('Confirm that this is a real instrument recording, not generated audio.')
        label=validate_label(body.get('label',{}))
        strength=body.get('pluckStrength','normal')
        if strength not in ('soft','normal','hard'):
            raise ValueError('Choose soft, normal or hard pluck strength.')
        label['pluckStrength']=strength
        if body.get('source') not in ('microphone','WAV upload'):
            raise ValueError('Unknown recording source.')
        raw=base64.b64decode(body.get('audio',''),validate=True)
        if len(raw)%4 or len(raw)>192000*4*10:
            raise ValueError('Audio is invalid or exceeds ten seconds.')
        rate=int(body.get('sampleRate',0))
        audio=np.frombuffer(raw,dtype='<f4')
        if rate <= 0 or len(audio)>rate*10:
            raise ValueError('Recording exceeds ten seconds.')
        # Save the full captured PCM; preview normalization does not change this source.
        return self.library.add_real(audio,rate,label,body['source'],
                                     str(body.get('filename',''))[:200],str(body.get('session',''))[:100])

    def generate(self, body: dict) -> dict:
        hz=float(body.get('frequencyHertz',0));duration=float(body.get('duration',.8))
        validate_request(hz,duration)
        course=body.get('course')
        if course not in ('ust','orta','alt'):
            raise ValueError('Choose a course.')
        method=body.get('method','neural')
        seed=int(body.get('seed',7))
        if not 0 <= seed <= 2**32-1:
            raise ValueError('Seed must be a whole number from 0 to 4294967295.')
        if method=='neural':
            if not self.model.exists():
                raise ValueError('Train a model first to use neural synthesis.')
            if hashlib.sha256(self.model.read_bytes()).hexdigest()!=self.model_id:
                raise ValueError('The model file changed. Restart the lab to load its new version and split metadata.')
            audio,details=neural(self.model,hz,course,duration,seed)
            model_id=self.model_id
        elif method=='sample':
            audio,details=sample(self.dataset,hz,course,duration,
                                 allowed_identities={key for key,value in self.usage.items() if value=='training'} if self.usage else None)
            model_id='sample-baseline'
        else:
            raise ValueError('Unknown synthesis method.')
        parameters=dict(frequencyHertz=hz,duration=duration,course=course,seed=seed,
                        referenceHertz=float(body.get('referenceHertz',440)),cents=float(body.get('cents',0)),
                        note=str(body.get('note',''))[:20],details=details)
        if not all(math.isfinite(parameters[k]) for k in ('referenceHertz','cents')):
            raise ValueError('Reference and cents must be finite.')
        return self.feedback.add_render(audio,parameters,str(model_id),method)


def make_handler(app: LabApplication):
    class Handler(BaseHTTPRequestHandler):
        server_version='BaglamaSoundML-local'

        def response(self, status: int, data, content_type='application/json', download: str | None = None):
            if content_type=='application/json':
                data=json.dumps(data,allow_nan=False).encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            if download:
                self.send_header('Content-Disposition',f'attachment; filename="{download}"')
            self.end_headers();self.wfile.write(data)

        def allowed_host(self):
            host=self.headers.get('Host','')
            return host in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

        def do_GET(self):
            if not self.allowed_host():
                return self.response(403,dict(error='Use this server through localhost.'))
            try:
                path=urlsplit(self.path).path
                parts=path.strip('/').split('/')
                if path in ('/','/lab','/lab/'):
                    return self.response(200,files('baglama_sound_ml').joinpath('resources/lab.html').read_bytes(),'text/html; charset=utf-8')
                assets={'/strum-string-fields.js':'text/javascript','/final-tone-examples.js':'text/javascript','/strum-microphone.js':'text/javascript','/final-tone-ui.js':'text/javascript','/lab.css':'text/css','/lab.js':'text/javascript','/capture-worklet.js':'text/javascript','/lab-audio.js':'text/javascript','/capture-ui.js':'text/javascript'}
                if path in assets:
                    return self.response(200,files('baglama_sound_ml').joinpath('resources'+path).read_bytes(),assets[path])
                if path=='/playground/index.html':
                    self.send_response(302);self.send_header('Location','/');self.end_headers();return
                if path=='/api/health':
                    return self.response(200,dict(service='BaglamaSoundML',projectId=app.project_id))
                if path=='/api/config':
                    return self.response(200,app.config())
                if path=='/api/samples':
                    return self.response(200,dict(samples=app.samples(parse_qs(urlsplit(self.path).query).get('trash')==['1'])))
                if path=='/api/final-tone-tests':
                    return self.response(200,dict(cases=app.final_tone_cases.rows(parse_qs(urlsplit(self.path).query).get('trash')==['1'])))
                if path=='/api/final-tone-tests/export':
                    return self.response(200,app.final_tone_cases.export(),'application/zip','BaglamaSoundML-final-tone-tests.zip')
                if len(parts)==4 and parts[:2]==['api','final-tone-tests'] and parts[3] in ('audio','pcm'):
                    audio,rate=app.final_tone_cases.audio(parts[2])
                    if parts[3]=='pcm':
                        return self.response(200,dict(audio=base64.b64encode(audio.astype('<f4').tobytes()).decode()))
                    return self.response(200,wav_bytes(audio,rate),'audio/wav')
                if path=='/api/renders':
                    return self.response(200,dict(renders=app.feedback.renders(parse_qs(urlsplit(self.path).query).get('trash')==['1'])))
                if path=='/api/feedback':
                    return self.response(200,app.feedback.report())
                if path=='/api/export/samples':
                    return self.response(200,app.library.export_real(),'application/zip','BaglamaSoundML-real-samples.zip')
                if path=='/api/export/feedback':
                    return self.response(200,json.dumps(app.feedback.report(),indent=2).encode(),'application/json; charset=utf-8','BaglamaSoundML-feedback.json')
                if len(parts)==4 and parts[:2]==['api','samples'] and parts[3]=='original':
                    audio,row=app.library.sample_audio(parts[2],original=True)
                    if row['deleted_at']:
                        raise KeyError('Sample is in Trash.')
                    return self.response(200,dict(audio=base64.b64encode(audio.astype('<f4').tobytes()).decode(),
                                                  sampleRate=row['rate'],identity=row['identity'],
                                                  startFrame=row['start_frame'] or 0,endFrame=row['end_frame'] or len(audio)))
                if len(parts)==4 and parts[:2] in (['api','samples'],['api','renders']) and parts[3]=='audio':
                    kind,identity=parts[1],parts[2]
                    if kind=='samples':
                        audio,rate=app.library.real_audio(identity)
                    else:
                        audio,rate=app.feedback.audio(identity),RATE
                    return self.response(200,wav_bytes(audio,rate,kind=='samples'),'audio/wav')
                if len(parts)==4 and parts[:2]==['api','comparisons'] and parts[3] in ('a','b'):
                    row=app.feedback.comparison_row(parts[2])
                    audio=app.feedback.audio(row[parts[3]+'_id'])
                    return self.response(200,wav_bytes(audio,RATE),'audio/wav')
                # Preserve existing generated reports/demos under outputs only.
                output_root=(app.project/'outputs').resolve()
                output=(output_root/unquote(path).lstrip('/')).resolve()
                types={'.html':'text/html; charset=utf-8','.json':'application/json; charset=utf-8','.wav':'audio/wav'}
                if output_root in output.parents and output.is_file() and output.suffix in types:
                    return self.response(200,output.read_bytes(),types[output.suffix])
                return self.response(404,dict(error='Not found.'))
            except (ValueError,KeyError,OSError,json.JSONDecodeError) as error:
                self.response(400 if not isinstance(error,KeyError) else 404,dict(error=str(error)))

        def do_POST(self):
            origin=self.headers.get('Origin','')
            allowed=(f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}')
            if not self.allowed_host() or origin not in allowed or not secrets.compare_digest(self.headers.get('X-Baglama-Token',''),app.token):
                return self.response(403,dict(error='Open the local app again before saving changes.'))
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=64*1024*1024:
                    raise ValueError('Request is empty or exceeds the local import limit.')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ValueError('Expected a JSON object.')
                path=urlsplit(self.path).path;parts=path.strip('/').split('/')
                if path=='/api/shutdown':
                    self.response(200,dict(stopped=True))
                    threading.Thread(target=self.server.shutdown,daemon=True).start()
                    return
                if path=='/api/recordings':
                    return self.response(400,dict(error='Import new samples as a Baglamator ZIP.'))
                if len(parts)==4 and parts[:2]==['api','samples'] and parts[3]=='trim':
                    return self.response(200,app.library.trim(parts[2],body.get('startFrame'),body.get('endFrame'),
                                                              body.get('expectedIdentity')))
                if path=='/api/final-tone-tests':
                    raw=base64.b64decode(body.get('audio',''),validate=True)
                    if len(raw)%4 or len(raw)>192000*4*8:raise ValueError('Invalid strum PCM.')
                    return self.response(200,app.final_tone_cases.save(np.frombuffer(raw,dtype='<f4'),body.get('sampleRate',0),float(body.get('referenceHertz',440)),body))
                if len(parts)==4 and parts[:2]==['api','final-tone-tests'] and parts[3] in ('trash','restore'):
                    return self.response(200,app.final_tone_cases.trash(parts[2],parts[3]=='restore'))
                if path=='/api/final-tone':
                    reference=float(body.get('referenceHertz',440))
                    if body.get('demo') is True:
                        if not math.isfinite(reference) or not 400<=reference<=480:
                            raise ValueError('A4 must be between 400 and 480 Hz.')
                        audio,rate=synthetic_strum(reference)
                    else:
                        raw=base64.b64decode(body.get('audio',''),validate=True)
                        if len(raw)%4 or len(raw)>192000*4*8:
                            raise ValueError('Choose at most eight seconds of valid PCM audio.')
                        audio=np.frombuffer(raw,dtype='<f4')
                        rate=body.get('sampleRate',0)
                    return self.response(200,detect_final_tone(audio,rate,reference))
                if path=='/api/import':
                    content=base64.b64decode(body.get('archive',''),validate=True)
                    return self.response(200,app.library.import_archive(io.BytesIO(content),Path(str(body.get('filename','Imported ZIP'))).name))
                if path=='/api/renders':
                    return self.response(200,app.generate(body))
                if path=='/api/continuations':
                    if not app.model.is_file() or not (app.dataset/'manifest.json').is_file():
                        raise ValueError('Train a local model and restart the app with its matching dataset to run this experiment.')
                    name='continuation-'+secrets.token_hex(8)
                    result=compare_continuations(app.dataset,app.model,app.project/'outputs'/name)
                    return self.response(200,dict(report=f'/{name}/index.html',
                                                  recordings=result['recordings'],
                                                  skipped=len(result['skipped'])))
                if path=='/api/comparisons':
                    return self.response(200,app.feedback.comparison(str(body.get('first','')),str(body.get('second',''))))
                if len(parts)==4 and parts[0]=='api' and parts[1] in ('samples','renders') and parts[3] in ('trash','restore'):
                    app.library.trash(parts[1],parts[2],parts[3]=='restore')
                    return self.response(200,dict(saved=True))
                if len(parts)==4 and parts[:2]==['api','renders'] and parts[3]=='feedback':
                    return self.response(200,app.feedback.rate(parts[2],body))
                if len(parts)==4 and parts[:2]==['api','comparisons'] and parts[3]=='feedback':
                    return self.response(200,app.feedback.prefer(parts[2],body))
                return self.response(404,dict(error='Not found.'))
            except (ValueError,KeyError,OSError,TypeError,OverflowError,zipfile.BadZipFile) as error:
                self.response(400,dict(error=str(error)))
    return Handler


def serve(project: Path, library: Path, model: Path, samples: Path | None = None, port: int = 8765, dataset: Path | None = None):
    if not 1024 <= port <= 65535:
        raise ValueError('Choose a port from 1024 to 65535.')
    # Check availability before importing/writing state; never stop somebody else's server.
    check=socket.socket()
    check.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
    try:
        check.bind(('127.0.0.1',port))
    except OSError as error:
        from urllib.request import urlopen
        try:
            with urlopen(f'http://127.0.0.1:{port}/api/health',timeout=1) as response:
                health=json.load(response)
            expected=hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
            if health.get('service')=='BaglamaSoundML' and health.get('projectId')==expected:
                print(f'BaglamaSoundML is already running: http://127.0.0.1:{port}/\nUse the original Terminal window and Ctrl+C to stop it.',flush=True)
                return
        except (OSError,ValueError):
            pass
        raise ValueError(f'Port {port} is in use. Stop the old server or use --port {port+1}.') from error
    finally:
        check.close()
    app=LabApplication(project,library,model,dataset)
    if samples:
        print('Existing sample import:',app.library.import_folder(samples),flush=True)
    server=ThreadingHTTPServer(('127.0.0.1',port),make_handler(app))
    print(f'BaglamaSoundML: http://127.0.0.1:{port}/\nLocal data: {app.library.root}\nCtrl+C or ./scripts/listen.sh --stop stops the server. No recording starts automatically.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nStopped.',flush=True)
    finally:
        server.server_close()


def stop_server(project: Path, port: int = 8765):
    from urllib.request import urlopen, Request
    from urllib.error import URLError
    root=f'http://127.0.0.1:{port}'
    try:
        with urlopen(root+'/api/health',timeout=2) as response:
            health=json.load(response)
    except URLError:
        print(f'No BaglamaSoundML server is responding on port {port}.',flush=True)
        return
    expected=hashlib.sha256(str(project.resolve()).encode()).hexdigest()[:16]
    if health.get('service')!='BaglamaSoundML' or health.get('projectId')!=expected:
        raise ValueError('That port belongs to a different service or project; it was not stopped.')
    with urlopen(root+'/api/config',timeout=2) as response:
        token=json.load(response)['token']
    request=Request(root+'/api/shutdown',data=b'{}',headers={
        'Content-Type':'application/json','Origin':root,'X-Baglama-Token':token})
    with urlopen(request,timeout=2) as response:
        json.load(response)
    print('BaglamaSoundML server stopped.',flush=True)
