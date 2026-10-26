import json
import shutil
import tempfile
import unittest
from pathlib import Path
from test_exporter import make_record
import inper_exporter as ex


class DatasetTests(unittest.TestCase):
    def test_nested_identity_stable_ids_relative_details_and_move(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            batch = root / '2026-10-08 Metabolic Sensor NPR E'
            make_record(batch, 'ATP Sensor/01 #1043')
            make_record(batch, 'ATP Sensor/01 #1043', '20261013112752')
            out = root / 'out'
            ex.run_export([batch], out, log=lambda _: None)
            m = json.loads((out / 'dataset.json').read_text())
            self.assertEqual(len(m['recordings']), 2)
            self.assertEqual(len({r['recording_id'] for r in m['recordings']}), 2)
            for r in m['recordings']:
                self.assertEqual(r['animal_id'], '#1043')
                self.assertEqual(r['sensor'], 'ATP Sensor')
                self.assertEqual(r['condition'], 'Encoding')
                self.assertFalse(r['identity_confirmed'])
            moved = root / 'moved'
            shutil.move(str(out), moved)
            for r in m['recordings']:
                meta_file = moved / r['metadata']
                meta = json.loads(meta_file.read_text())
                detail = (meta_file.parent / meta['detailed_csv_relative_to_metadata']).resolve()
                self.assertEqual(ex.digest(detail), r['detailed_csv_sha256'])
            again = root / 'again'
            ex.run_export([batch], again, log=lambda _: None)
            self.assertEqual(m['dataset_id'], json.loads((again / 'dataset.json').read_text())['dataset_id'])

    def test_ambiguous_and_timestamp_only_are_unconfirmed(self):
        from dataset_manifest import identity
        b = Path('batch')
        for path in ('20261013112751', '#1 #2/20261013112751'):
            self.assertEqual(identity(b, b / path)['animal_id'], '')

    def test_long_output_path_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            batch = root / 'NPR E'
            make_record(batch)
            output = root / ('x' * 190) / 'output'
            with self.assertRaisesRegex(ex.ExportError, 'shorter output root'):
                ex.run_export([batch], output, log=lambda _: None)
            self.assertFalse(output.exists())
