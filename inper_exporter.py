"""Read-only Inper SQLite export, extracted from the validated 2026-10-15 workflow.

Standard-library only. No vendor DLL, MATLAB, network or inference of behavior.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import itertools
import json
import math
import re
import shutil
import sqlite3
import struct
from collections import Counter
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

VERSION = "1.1.0"
EVENT_TABLES = ("Marker", "OutputMarker", "Tag", "Note", "Tracking", "ZoneInfo", "IntervalScale")


class ExportError(Exception):
    pass


def require(condition, message):
    if not condition:
        raise ExportError(message)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_db(path):
    for suffix in ("-wal", "-journal"):
        sidecar = Path(str(path) + suffix)
        require(not sidecar.exists() or sidecar.stat().st_size == 0,
                f"Close acquisition software/checkpoint DB first; active sidecar: {sidecar}")
    con = sqlite3.connect(Path(path).as_uri() + "?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def json_safe(value):
    if isinstance(value, bytes):
        return {"__blob_base64__": base64.b64encode(value).decode("ascii")}
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    return value


def write_json(path, obj):
    with Path(path).open("x", encoding="utf-8") as f:
        json.dump(json_safe(obj), f, ensure_ascii=False, indent=2, allow_nan=False)


def write_csv(path, header, data):
    with Path(path).open("x", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, lineterminator="\r\n")
        writer.writerow(header)
        writer.writerows(data)


def timespan(ns):
    ticks = ns // 100
    whole, frac = divmod(ticks, 10_000_000)
    days, rest = divmod(whole, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, seconds = divmod(rest, 60)
    return f"{days}:{hours:02d}:{minutes:02d}:{seconds:02d}.{frac:07d}"


def seconds(ns):
    return f"{ns // 1_000_000_000}.{ns % 1_000_000_000:09d}"


def decode(value, expected):
    values = {}
    for token in value.split():
        roi, payload = token.split(",", 1)
        roi = int(roi)
        raw = base64.b64decode(payload, validate=True)
        require(roi not in values and len(raw) == 8, "Duplicate ROI or invalid float64 payload")
        number = struct.unpack("<d", raw)[0]
        require(math.isfinite(number), "Nonfinite signal: export stopped, no replacement applied")
        values[roi] = number
    require(set(values) == set(expected), f"Record ROI IDs {sorted(values)} != configuration {expected}")
    return values


def load_record(db):
    before = digest(db)
    with closing(read_db(db)) as con:
        require(con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", f"Invalid SQLite DB: {db}")
        schema = dict(con.execute("SELECT name,sql FROM sqlite_master WHERE type='table'"))
        require("ChannelConfig" in schema, f"Not a supported Inper DB: {db}")
        channels = [dict(r) for r in con.execute('SELECT * FROM "ChannelConfig" ORDER BY Id')]
        require(bool(channels), "Empty ChannelConfig")
        mappings = {}
        roi_names = {}
        for row in channels:
            require(row.get("Type") == "Camera" and not row.get("IsDelete", 0),
                    "Only active Camera channels are supported; inspect ChannelConfig")
            match = re.fullmatch(r"(410|470)\s*nm", row["LightName"])
            require(match is not None, f"Unsupported wavelength: {row['LightName']}")
            wave, light, roi = int(match[1]), int(row["LightId"]), int(row["ChannelId"])
            require(light >= 0 and roi >= 0, "Negative channel ID")
            require((wave, roi) not in mappings, "Duplicate wavelength/ROI configuration")
            mappings[wave, roi] = light
            name = row["ChannelName"]
            require(bool(re.fullmatch(r"ROI-[1-9][0-9]*", name)), f"Unsupported ROI name: {name}")
            require(roi not in roi_names or roi_names[roi] == name, "ROI name differs by wavelength")
            roi_names[roi] = name
        rois = sorted(roi_names)
        require(len(set(roi_names.values())) == len(rois), "Duplicate ROI names")
        light_ids = {}
        for wave in (410, 470):
            require(all((wave, roi) in mappings for roi in rois), "Each ROI must have both 410 and 470")
            ids = {mappings[wave, roi] for roi in rois}
            require(len(ids) == 1, "Mixed LightId within wavelength")
            light_ids[wave] = ids.pop()
        require(light_ids[410] != light_ids[470], "410 and 470 must use different LightId")
        expected = {f"AllChannelRecord{x}" for x in light_ids.values()}
        actual = {x for x in schema if x.startswith("AllChannelRecord")}
        require(actual == expected, f"Unexpected signal tables: {actual}; expected {expected}")
        data = {}
        for wave, light in light_ids.items():
            rows = [dict(r) for r in con.execute(
                f"SELECT * FROM {quote('AllChannelRecord' + str(light))} ORDER BY CameraTime,Id")]
            require(bool(rows), f"Empty {wave} signal table")
            last = -1
            for row in rows:
                ns = row["CameraTime"]
                require(isinstance(ns, int) and ns > last and ns >= 0, "Nonmonotonic/invalid CameraTime")
                require(row["Type"] == light, "Record Type differs from LightId")
                last = ns
                row["decoded"] = decode(row["Value"], rois)
            data[wave] = rows
        tables = {name: [dict(r) for r in con.execute(f"SELECT * FROM {quote(name)}")]
                  for name in schema if name not in expected and name != "sqlite_sequence"}
    require(digest(db) == before, f"Source DB changed while reading: {db}")
    return dict(rois=rois, roi_names=roi_names, data=data, tables=tables, schema=schema, db_sha256=before)


@dataclass
class Job:
    batch: Path
    mouse: Path
    session: Path
    target: Path  # relative to output root
    stem: str

    @property
    def db(self):
        return self.session / "data.db"


def safe_name(text):
    require(text not in ("", ".", "..") and not re.search(r'[<>:"/\\|?*\x00-\x1f]', text),
            f"Unsafe filename: {text}")
    return text


def scan(batches, output=None, log=lambda text: None):
    batches = [Path(x).resolve() for x in batches]
    require(bool(batches), "Select at least one batch folder")
    require(len({p.name.casefold() for p in batches}) == len(batches), "Batch folder names must be unique")
    for a in batches:
        require(a.is_dir(), f"Missing batch folder: {a}")
        require(not a.is_symlink(), "Symlink batch roots are not supported")
        for b in batches:
            require(a == b or not a.is_relative_to(b), "Selected batches must not overlap")
        if output is not None:
            out = Path(output).resolve()
            require(not out.is_relative_to(a) and not a.is_relative_to(out), "Output and input must not overlap")
    jobs, skipped, warnings = [], [], []
    for batch in batches:
        dbs = sorted(batch.rglob("data.db"))
        require(bool(dbs), f"No data.db found in {batch}")
        for item in batch.rglob("*"):
            require(not item.is_symlink(), f"Symlink not supported: {item}")
            if item.is_dir() and not any(item.iterdir()):
                skipped.append({"batch": batch.name, "source_folder": str(item), "reason": "empty_directory"})
        counts = Counter(db.relative_to(batch).parts[0] for db in dbs)
        for db in dbs:
            rel = db.relative_to(batch)
            require(len(rel.parts) >= 3, f"Expected batch/animal/session/data.db: {db}")
            mouse = batch / rel.parts[0]
            session = db.parent
            videos = list(session.glob("*.avi"))
            require(len(videos) == 1, f"Expected exactly one AVI in {session}, found {len(videos)}")
            target = Path(batch.name) / mouse.name
            suffix = ""
            if counts[mouse.name] > 1:
                sub = session.relative_to(mouse)
                target /= sub
                suffix = "_" + "_".join(sub.parts)
            prefix = re.sub(r"^(\d{4}-\d{2}-\d{2})\s+", r"\1_", batch.name, count=1)
            mouse_stem = re.sub(r"\s+", "_", mouse.name, count=1)
            stem = safe_name(prefix + "_" + mouse_stem + suffix)
            log(f"Checking {batch.name} / {mouse.name} / {session.name}")
            record = load_record(db)
            n410, n470 = (len(record["data"][w]) for w in (410, 470))
            if n410 != n470:
                warnings.append(f"{db}: 410={n410}, 470={n470}; detailed CSV preserves all samples")
            jobs.append(Job(batch, mouse, session, target, stem))
        # Other nonempty session branches must not silently disappear.
        for mouse in (p for p in batch.iterdir() if p.is_dir()):
            for session in (p for p in mouse.iterdir() if p.is_dir()):
                if any(session.rglob("*")):
                    require(any(db.is_relative_to(session) for db in dbs),
                            f"Nonempty session has no data.db; inspect rather than skip: {session}")
    keys = [str(j.target / j.stem).casefold() for j in jobs]
    require(len(set(keys)) == len(keys), "Output naming collision")
    return jobs, skipped, warnings


def headers(record):
    names = record["roi_names"]
    primary = ["Time"] + [f"{names[r]}_sig_{w}" for r in record["rois"] for w in (410, 470)] + [""]
    detail = ["SampleIndex"]
    for w in (410, 470):
        detail += [f"Time_{w}_s"] + [f"{names[r]}_sig_{w}" for r in record["rois"]]
    detail += [f"{key}_{w}" + ("_ns" if key == "CameraTime" else "")
               for key in ("CameraTime", "CreateTime", "RecordId") for w in (410, 470)]
    return primary, detail


def primary_rows(record):
    data = record["data"]
    for i, row in enumerate(data[410]):
        yield [timespan(row["CameraTime"])] + [
            repr(data[w][i]["decoded"][r]) if i < len(data[w]) else ""
            for r in record["rois"] for w in (410, 470)] + [""]


def detailed_rows(record, header):
    for i, pair in enumerate(itertools.zip_longest(record["data"][410], record["data"][470]), 1):
        output = {"SampleIndex": i}
        for w, row in zip((410, 470), pair):
            if row is None:
                continue
            output.update({f"Time_{w}_s": seconds(row["CameraTime"]), f"CameraTime_{w}_ns": row["CameraTime"],
                           f"CreateTime_{w}": row["CreateTime"], f"RecordId_{w}": row["Id"]})
            output.update({f"{record['roi_names'][r]}_sig_{w}": repr(row["decoded"][r]) for r in record["rois"]})
        yield [output.get(key, "") for key in header]


def verify_csv(path, header, expected):
    # Exact text comparison preserves raw integer times, empty tails and float roundtrips.
    count = 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        require(next(reader) == header, f"Header mismatch: {path}")
        for got, wanted in itertools.zip_longest(reader, expected):
            require(got is not None and wanted is not None and got == [str(x) for x in wanted],
                    f"CSV read-back mismatch, row {count + 1}: {path}")
            count += 1
    return count


def export_job(job, root, copy_videos, log):
    record = load_record(job.db)
    sources = sorted(set(p for p in job.session.rglob("*") if p.is_file()) |
                     set(job.mouse.glob("*.txt")))
    before = {str(p): digest(p) for p in sources}
    require(before[str(job.db)] == record["db_sha256"], "DB changed after validation")
    target = root / job.target
    target.mkdir(parents=True, exist_ok=True)
    primary = target / (job.stem + "(Camera).csv")
    detailed = root / "_details" / job.target / (job.stem + "_detailed.csv")
    detailed.parent.mkdir(parents=True, exist_ok=True)
    ph, dh = headers(record)
    write_csv(primary, ph, primary_rows(record))
    write_csv(detailed, dh, detailed_rows(record, dh))
    nprimary = verify_csv(primary, ph, primary_rows(record))
    ndetail = verify_csv(detailed, dh, detailed_rows(record, dh))
    # Verify the serialized numeric values against original base64 IEEE754 payload bytes.
    with detailed.open(encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f)):
            for w in (410, 470):
                if i < len(record["data"][w]):
                    raw = record["data"][w][i]
                    for token in raw["Value"].split():
                        r, payload = token.split(",", 1)
                        actual = struct.pack("<d", float(row[f"{record['roi_names'][int(r)]}_sig_{w}"]))
                        require(actual == base64.b64decode(payload), "Float64 roundtrip mismatch")
    video = next(job.session.glob("*.avi"))
    video_target = target / (job.stem + ".avi") if copy_videos else video
    if copy_videos:
        require(not video_target.exists(), "Refusing video overwrite")
        shutil.copy2(video, video_target)
        require(digest(video_target) == before[str(video)], "Video copy hash mismatch")
    notes = []
    for note in job.mouse.glob("*.txt"):
        dest = target / note.name
        if dest.exists():
            require(digest(dest) == before[str(note)], "Note name collision")
        else:
            shutil.copy2(note, dest)
        require(digest(dest) == before[str(note)], "Note copy hash mismatch")
        notes.append(str(dest.relative_to(root)))
    # All non-signal table rows are retained in JSON; nonempty event tables also get CSVs.
    events = {}
    for name in EVENT_TABLES:
        table = record["tables"].get(name, [])
        events[name] = len(table)
        if table:
            event_csv = target / (job.stem + "_source_" + name + ".csv")
            keys = list(table[0])
            write_csv(event_csv, keys, ([json.dumps(json_safe(v), ensure_ascii=False) if isinstance(v, bytes) else v
                                        for v in row.values()] for row in table))
    after_paths = sorted(set(p for p in job.session.rglob("*") if p.is_file()) |
                         set(job.mouse.glob("*.txt")))
    after = {str(p): digest(p) for p in after_paths}
    require(before == after, "Source files changed during export")
    n410, n470 = (len(record["data"][w]) for w in (410, 470))
    metadata = target / (job.stem + "_metadata.json")
    write_json(metadata, dict(exporter_version=VERSION, source_database=str(job.db),
        method="Read-only SQLite; Base64 little-endian IEEE754 float64; no vendor GUI comparison",
        source_schema=record["schema"], source_tables=record["tables"], source_file_sha256=before,
        primary_header=ph, detailed_header=dh, event_table_counts=events, copied_notes=notes,
        csv_columns=ph, detailed_csv_columns=dh, detailed_csv=str(detailed),
        detailed_csv_relative_to_output=str(detailed.relative_to(root)), detailed_csv_sha256=digest(detailed),
        sample_counts={"410": len(record["data"][410]), "470": len(record["data"][470])},
        time_rule="Primary uses 410 CameraTime//100 ticks; detailed preserves independent nanosecond times",
        alignment="By sample index, not interpolated; no video synchronization inferred",
        source_unchanged=True))
    result = dict(batch=job.batch.name, animal_folder=job.mouse.name, source_session=str(job.session),
        source_database=str(job.db), csv=str(primary.relative_to(root)), detailed_csv=str(detailed.relative_to(root)),
        metadata=str(metadata.relative_to(root)), video=str(video_target.relative_to(root)) if copy_videos else str(video),
        video_copied=copy_videos, samples_410=n410, samples_470=n470, primary_rows=nprimary, detailed_rows=ndetail,
        roi_count=len(record["rois"]), extra_470_samples_in_details=max(0, n470-n410),
        missing_470_primary_tail_rows=max(0, n410-n470), source_event_rows=sum(events.values()),
        csv_sha256=digest(primary), detailed_csv_sha256=digest(detailed), video_sha256=before[str(video)],
        source_db_sha256=record["db_sha256"], validation="PASS")
    log(f"PASS {job.batch.name} / {job.mouse.name}: 410={n410}, 470={n470}, ROI={len(record['rois'])}")
    return result


def run_export(batches, output, copy_videos=True, log=print):
    output = Path(output).resolve()
    require(not output.exists(), "Output folder already exists. Select a NEW folder; overwrite/resume is disabled.")
    jobs, skipped, warnings = scan(batches, output, log)
    require(not output.exists(), "Output folder appeared during preflight")
    output.mkdir(parents=True, exist_ok=False)
    started = datetime.now(timezone.utc).isoformat()
    records = []
    try:
        for job in jobs:
            records.append(export_job(job, output, copy_videos, log))
        write_csv(output / "conversion_manifest.csv", list(records[0]), (r.values() for r in records))
        write_csv(output / "skipped_empty_folders.csv", ["batch", "source_folder", "reason"],
                  (r.values() for r in skipped))
        write_json(output / "validation_summary.json", dict(version=VERSION, status="PASS", started_utc=started,
            completed_utc=datetime.now(timezone.utc).isoformat(), records=len(records),
            skipped_empty_folders=len(skipped), copied_videos=len(records) if copy_videos else 0,
            warnings=warnings, gui_export_comparison_performed=False,
            detailed_signal_values_verified=sum(r["roi_count"]*(r["samples_410"]+r["samples_470"]) for r in records),
            extra_470_samples_retained=sum(r["extra_470_samples_in_details"] for r in records),
            missing_470_tail_rows=sum(r["missing_470_primary_tail_rows"] for r in records)))
        (output / "OUTPUT_README.txt").write_text(
            "SUCCESS: see validation_summary.json and conversion_manifest.csv.\n"
            "Use batch/animal/*(Camera).csv for sample-compatible import.\n"
            "Primary Time is 410 nm only; signals are paired by sample index.\n"
            "_details retains ALL samples and independent 410/470 nanosecond timestamps.\n"
            "Missing values are blank, never zero. No interpolation/filter/dF/F was applied.\n"
            "Metadata retains source tables/events; source events are not Analyzer annotations.\n"
            "Video offset still requires manual confirmation.\n"
            + ("Videos are copied and SHA256 verified.\n" if copy_videos else
               "VIDEOS NOT COPIED: manifest references originals; keep original paths available.\n"), encoding="utf-8")
    except Exception as exc:
        write_json(output / "FAILED.json", dict(status="FAILED", error=str(exc), completed_records=records,
            instructions="Do not analyze this incomplete output. Fix cause and use a different new output folder."))
        raise
    log(f"COMPLETE: {len(records)} records; {len(skipped)} empty folders skipped. Output: {output}")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", action="append", required=True, help="Input batch folder; repeat for more batches")
    parser.add_argument("--output", required=True, help="NEW output folder, must not exist")
    parser.add_argument("--scan-only", action="store_true", help="Read-only preflight; creates no output")
    parser.add_argument("--link-videos", action="store_true", help="Keep originals in place instead of copying AVI")
    args = parser.parse_args()
    try:
        if args.scan_only:
            jobs, skipped, warnings = scan(args.batch, args.output, print)
            for w in warnings:
                print("WARNING:", w)
            print(f"SCAN PASS: {len(jobs)} records, {len(skipped)} empty folders; no output written")
        else:
            run_export(args.batch, args.output, not args.link_videos)
    except Exception as exc:
        parser.exit(1, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
