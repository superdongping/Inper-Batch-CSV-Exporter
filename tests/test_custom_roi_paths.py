import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing
from unittest.mock import patch
import tkinter as tk
import inper_exporter as ex
from inper_exporter_gui import ExporterApp
from path_helpers import display_path, suggested_output, overlap
from test_exporter import make_record


class CompatibilityTests(unittest.TestCase):
    def test_custom_labels_keep_values_and_mapping(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); batch = root/'input'; db = make_record(batch)
            original = ex.load_record(db)
            with closing(sqlite3.connect(db)) as con, con:
                con.execute('UPDATE ChannelConfig SET ChannelName=? WHERE ChannelId=0', ('ROI-1-L',))
                con.execute('UPDATE ChannelConfig SET ChannelName=? WHERE ChannelId=1', ('Right DG / \u53f3\u4fa7',))
            before = ex.digest(db)
            record = ex.load_record(db)
            self.assertEqual(record['data'], original['data'])
            out = root/'out'
            result = ex.run_export([batch], out, log=lambda s: None)[0]
            meta = json.loads((out/result['metadata']).read_text(encoding='utf-8'))
            self.assertEqual(meta['roi_mapping'][0], dict(channel_id=0, source_name='ROI-1-L', csv_name='ROI-1'))
            self.assertEqual(meta['roi_mapping'][1]['source_name'], 'Right DG / \u53f3\u4fa7')
            with (out/result['csv']).open(encoding='utf-8-sig', newline='') as f:
                rows = list(csv.reader(f))
            self.assertEqual(rows[0], ex.headers(original)[0])
            self.assertEqual(rows[1:], [[str(v) for v in r] for r in ex.primary_rows(original)])
            self.assertEqual(before, ex.digest(db))

    def test_duplicate_labels_use_distinct_channel_ids(self):
        with tempfile.TemporaryDirectory() as temp:
            db=make_record(Path(temp)/'input')
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("UPDATE ChannelConfig SET ChannelName='DG'")
            self.assertEqual(ex.load_record(db)['roi_names'], {0:'ROI-1',1:'ROI-2'})

    def test_inconsistent_wave_labels_still_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            db=make_record(Path(temp)/'input')
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("UPDATE ChannelConfig SET ChannelName='other' WHERE Id=1")
            with self.assertRaisesRegex(ex.ExportError, 'differs by wavelength'):
                ex.load_record(db)

    def test_unc_display_boundary(self):
        maps={'J:':r'\\ad.unc.edu\med\pharm\Groups'}
        self.assertEqual(display_path(r'\\ad.unc.edu\med\pharm\Groups\Song_Lab',maps),r'J:\Song_Lab')
        self.assertTrue(display_path(r'\\ad.unc.edu\med\pharm\GroupsOther\x',maps).startswith('\\\\'))

    def test_safe_suggestion_overlap_and_existing(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); batch=root/'input'; batch.mkdir()
            out=Path(suggested_output([batch],batch/'nested'))
            self.assertFalse(overlap(out,batch)); self.assertFalse(out.exists())
            out.mkdir(parents=True)
            self.assertNotEqual(Path(suggested_output([batch],batch/'nested')),out)
            for invalid in [batch,batch/'output',root]:
                with self.assertRaisesRegex(ex.ExportError,'Input:'):
                    ex.validate_output([batch],invalid)
            ex.validate_output([batch],root/'input_other'/'out')

    def test_gui_preserves_drive_and_rejects_overlap_before_worker(self):
        with tempfile.TemporaryDirectory() as temp:
            root=tk.Tk(); root.withdraw()
            try:
                app=ExporterApp(root); batch=Path(temp)/'input'; batch.mkdir()
                with patch('inper_exporter_gui.filedialog.askdirectory',return_value=str(batch)):
                    app.add_batch()
                self.assertEqual(app.batches,[display_path(batch)])
                self.assertFalse(overlap(app.output.get(),batch))
                app.output.set(str(batch/'bad'))
                with patch('inper_exporter_gui.messagebox.showerror') as error:
                    app.start_scan(); error.assert_called_once()
                self.assertFalse(app.busy)
            finally:
                root.destroy()
