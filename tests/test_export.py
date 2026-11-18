import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
from baglama_sound_ml.export import export_swift, playground


class ExportTests(unittest.TestCase):
    def test_portable_model_omits_training_identities_and_embeds_standalone(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            weights={}
            for layer,inputs,outputs in ((0,5,48),(2,48,48),(4,48,25)):
                weights[f'{layer}.weight']=np.zeros((outputs,inputs),dtype=np.float32)
                weights[f'{layer}.bias']=np.zeros(outputs,dtype=np.float32)
            weights.update(mean=np.full(25,-3),scale=np.ones(25),metadata=np.array(json.dumps(dict(
                schema_version=1,training_identities=['private-capture-id'],
                frequency_ranges_hz={'ust':[98,220],'orta':[174,196],'alt':[130,293]}))))
            model=root/'model.npz'
            np.savez(model,**weights)
            export_swift(model,root/'model.json')
            payload=json.loads((root/'model.json').read_text())
            self.assertEqual(len(payload['layers'][0]['weights'][0]),5)
            self.assertNotIn('private-capture-id',(root/'model.json').read_text())
            playground(model,root/'page.html')
            page=(root/'page.html').read_text()
            self.assertNotIn('__BAGLAMA_MODEL__',page)
            self.assertNotIn('private-capture-id',page)
            self.assertIn('Generate &amp; play',page)
