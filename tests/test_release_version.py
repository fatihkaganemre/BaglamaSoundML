import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('check_release',Path(__file__).resolve().parents[1]/'scripts/check_release.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

class ReleaseVersionTests(unittest.TestCase):
    def test_stable_version_matches_package(self):
        self.assertEqual(module.validate_release('v0.1.0','0.1.0'),'0.1.0')
        self.assertEqual(module.validate_release('v1.12.34','1.12.34'),'1.12.34')
    def test_mismatched_or_unsafe_tags_are_rejected(self):
        for tag in ['0.1.0','v0.1','v00.1.0','v0.01.0','v0.1.0-rc.1','v0.1.0+build','v0.1.0\n','v0.1.0;echo unexpected','v1.0.0']:
            with self.subTest(tag=tag),self.assertRaises(ValueError):module.validate_release(tag,'0.1.0')
