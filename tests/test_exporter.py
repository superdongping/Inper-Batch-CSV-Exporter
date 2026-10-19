import base64
import csv
import json
import sqlite3
import struct
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

import inper_exporter as ex


def make_record(batch, mouse="01 #16", session="20261013112751", rois=2, counts=(3, 4)):
    folder = batch / mouse / session
    folder.mkdir(parents=True)
    (folder / "camera.avi").write_bytes(b"synthetic AVI bytes; no real video content")
    db = folder / "data.db"
    with closing(sqlite3.connect(db)) as con, con:
        con.execute("CREATE TABLE ChannelConfig(Id INTEGER PRIMARY KEY,ChannelId INTEGER,LightId INTEGER,ChannelName TEXT,LightName TEXT,Type TEXT,IsDelete INTEGER)")
        for light, wave in enumerate((410, 470)):
            for roi in range(rois):
                con.execute("INSERT INTO ChannelConfig VALUES(?,?,?,?,?,?,?)",
                            (light * rois + roi + 1, roi, light, f"ROI-{roi+1}", f"{wave} nm", "Camera", 0))
            con.execute(f"CREATE TABLE AllChannelRecord{light}(Id INTEGER PRIMARY KEY,Value TEXT,Type INTEGER,CameraTime INTEGER,CreateTime TEXT)")
            for index in range(counts[light]):
                values = [(-0.0 if index == roi == light == 0 else (index+1)*0.12345678901234567+roi+light)
                          for roi in range(rois)]
                payload = " ".join(f"{roi},"+base64.b64encode(struct.pack("<d", value)).decode()
                                   for roi, value in enumerate(values))
                con.execute(f"INSERT INTO AllChannelRecord{light} VALUES(?,?,?,?,?)",
                            (index+1, payload, light, index*50_000_000+light*25_000_000+123, "2026-10-13 11:27:51.1234567"))
        for table in ex.EVENT_TABLES:
            con.execute(f'CREATE TABLE "{table}"(Id INTEGER PRIMARY KEY,Name TEXT,Value BLOB)')
        con.execute('INSERT INTO "Tag" VALUES(1,?,?)', ("explore", b"\x00\xff"))
    return db


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.batch = self.root / "2026-10-13 Experiment Encoding"
        self.db = make_record(self.batch)
        (self.db.parent.parent / "20261013112700").mkdir()
        (self.db.parent.parent / "note.txt").write_text("mouse note", encoding="utf-8")
        self.out = self.root / "export"

    def tearDown(self):
        self.temp.cleanup()

    def run_export(self, **kwargs):
        return ex.run_export([self.batch], self.out, log=lambda text: None, **kwargs)

    def test_sample_header_full_precision_tail_events_and_hashes(self):
        hashes = {p: ex.digest(p) for p in self.batch.rglob("*") if p.is_file()}
        record = self.run_export()[0]
        primary = self.out / record["csv"]
        self.assertTrue(primary.read_bytes().startswith(b"\xef\xbb\xbfTime,"))
        self.assertNotIn(b"\n", primary.read_bytes().replace(b"\r\n", b""))
        with primary.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual(rows[0], ["Time", "ROI-1_sig_410", "ROI-1_sig_470", "ROI-2_sig_410", "ROI-2_sig_470", ""])
        self.assertEqual(rows[1][0], "0:00:00:00.0000001")
        self.assertEqual(rows[1][1], "-0.0")
        self.assertEqual(len(rows)-1, 3)
        with (self.out / record["detailed_csv"]).open(encoding="utf-8-sig", newline="") as f:
            detailed = list(csv.DictReader(f))
        self.assertEqual(len(detailed), 4)
        self.assertEqual(detailed[-1]["Time_410_s"], "")
        self.assertEqual(detailed[-1]["CameraTime_470_ns"], "175000123")
        self.assertEqual(record["extra_470_samples_in_details"], 1)
        self.assertEqual(record["source_event_rows"], 1)
        metadata = json.loads((self.out / record["metadata"]).read_text(encoding="utf-8"))
        self.assertEqual(Path(metadata["detailed_csv"]), self.out / record["detailed_csv"])
        self.assertEqual(ex.digest(metadata["detailed_csv"]), metadata["detailed_csv_sha256"])
        self.assertEqual(metadata["source_tables"]["Tag"][0]["Value"], {"__blob_base64__": "AP8="})
        self.assertTrue(list((self.out / record["csv"]).parent.glob("*_source_Tag.csv")))
        self.assertEqual(ex.digest(self.out / record["video"]), ex.digest(self.db.parent / "camera.avi"))
        self.assertEqual(hashes, {p: ex.digest(p) for p in self.batch.rglob("*") if p.is_file()})
        self.assertEqual(json.loads((self.out / "validation_summary.json").read_text())["status"], "PASS")

    def test_three_rois_large_imbalance_and_missing_tail(self):
        batch = self.root / "new type"
        make_record(batch, rois=3, counts=(5, 2))
        record = ex.run_export([batch], self.out, copy_videos=False, log=lambda text: None)[0]
        self.assertEqual(record["roi_count"], 3)
        self.assertEqual(record["missing_470_primary_tail_rows"], 3)
        self.assertFalse(record["video_copied"])
        self.assertTrue(Path(record["video"]).is_file())
        self.assertFalse(list(self.out.rglob("*.avi")))
        with (self.out / record["csv"]).open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
        self.assertEqual([rows[-1][j] for j in (2, 4, 6)], ["", "", ""])

    def test_multiple_recordings_one_animal_no_collision(self):
        make_record(self.batch, session="second")
        records = self.run_export()
        self.assertEqual(len(records), 2)
        self.assertEqual(len({r["csv"] for r in records}), 2)
        self.assertTrue(all("20261013112751" in records[0]["csv"] or "second" in r["csv"] for r in records))

    def test_scan_read_only_and_no_overwrite(self):
        jobs, skipped, warnings = ex.scan([self.batch], self.out)
        self.assertEqual((len(jobs), len(skipped), len(warnings)), (1, 1, 1))
        self.assertFalse(self.out.exists())
        self.run_export()
        hashes = {p: ex.digest(p) for p in self.out.rglob("*") if p.is_file()}
        with self.assertRaises(ex.ExportError):
            self.run_export()
        self.assertEqual(hashes, {p: ex.digest(p) for p in self.out.rglob("*") if p.is_file()})

    def test_invalid_source_rejected_before_output_creation(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE AllChannelRecord0 SET CameraTime=0")
        with self.assertRaises(ex.ExportError):
            self.run_export()
        self.assertFalse(self.out.exists())

    def test_unknown_wave_rejected(self):
        with closing(sqlite3.connect(self.db)) as con, con:
            con.execute("UPDATE ChannelConfig SET LightName='560 nm' WHERE LightId=1")
        with self.assertRaises(ex.ExportError):
            self.run_export()
        self.assertFalse(self.out.exists())

    def test_active_wal_and_missing_video_rejected(self):
        wal = Path(str(self.db) + "-wal")
        wal.write_bytes(b"active")
        with self.assertRaises(ex.ExportError):
            ex.load_record(self.db)
        wal.unlink()
        (self.db.parent / "camera.avi").unlink()
        with self.assertRaises(ex.ExportError):
            self.run_export()

    def test_missing_db_in_nonempty_session_not_silently_skipped(self):
        folder = self.db.parent.parent / "broken"
        folder.mkdir()
        (folder / "video.avi").write_bytes(b"video")
        with self.assertRaises(ex.ExportError):
            self.run_export()

    def test_overlap_and_duplicate_batch_names(self):
        with self.assertRaises(ex.ExportError):
            ex.scan([self.batch], self.batch / "output")
        with self.assertRaises(ex.ExportError):
            ex.scan([self.batch], self.root)
        with self.assertRaises(ex.ExportError):
            ex.scan([self.batch, self.batch], self.out)

    def test_timespan_days_and_nan_rejection(self):
        self.assertEqual(ex.timespan(90_061_123_456_789), "1:01:01:01.1234567")
        payload = base64.b64encode(struct.pack("<d", float("nan"))).decode()
        with self.assertRaises(ex.ExportError):
            ex.decode("0," + payload, [0])


if __name__ == "__main__":
    unittest.main()
