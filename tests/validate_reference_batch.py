"""Optional real-data regression. Outputs only to a NEW validation directory.

python tests/validate_reference_batch.py --reference PREVIOUS_EXPORT --output NEW_TEST_OUTPUT
Not run by unittest; no experimental data is bundled in the distribution.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import inper_exporter as ex


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reference = args.reference.resolve()
    with (reference / "conversion_manifest.csv").open(encoding="utf-8-sig", newline="") as f:
        previous = list(csv.DictReader(f))
    require = ex.require
    reference_paths = {Path(r[key]) for r in previous for key in ("csv", "detailed_csv", "video", "source_database")}
    reference_paths.add(reference / "sample data format 01 #1043(Camera).csv")
    before = {str(p): ex.digest(p) for p in reference_paths}
    batches = sorted({Path(r["source_database"]).parents[2] for r in previous})
    records = ex.run_export(batches, args.output, copy_videos=False, log=lambda text: print(text, flush=True))
    require(len(records) == len(previous), "Record count differs")
    old_by_db = {r["source_database"]: r for r in previous}
    for record in records:
        old = old_by_db[record["source_database"]]
        require(ex.digest(args.output / record["csv"]) == before[old["csv"]], "Primary CSV differs from reference")
        require(ex.digest(args.output / record["detailed_csv"]) == before[old["detailed_csv"]], "Detailed CSV differs from reference")
        require(record["video_sha256"] == before[old["video"]], "Video differs from reference")
    require(before == {str(p): ex.digest(p) for p in reference_paths}, "Reference/source changed")
    report = dict(status="PASS", records=len(records), primary_csv_byte_identical=True,
        detailed_csv_byte_identical=True, reference_and_source_hashes_unchanged=len(before),
        copied_real_videos=False, video_hashes_match=True)
    ex.write_json(args.output / "reference_regression.json", report)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
