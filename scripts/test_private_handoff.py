import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from email_verification import write_private_json


class PrivateHandoffTests(unittest.TestCase):
    def test_handoff_is_complete_and_private(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            write_private_json(path, {'state': 'waiting-for-code'})
            self.assertEqual(json.loads(path.read_text()), {'state': 'waiting-for-code'})
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
            if os.name != 'nt':
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_failed_write_preserves_previous_handoff(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'request.json'
            write_private_json(path, {'state': 'original'})
            with self.assertRaises(TypeError):
                write_private_json(path, {'invalid': object()})
            self.assertEqual(json.loads(path.read_text()), {'state': 'original'})
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])


if __name__ == '__main__':
    unittest.main()
