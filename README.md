# Inper Batch CSV Exporter V1.1

<img src="assets/inper-exporter.png" width="180" alt="Mouse with optical fiber, signal display and conversion folder">

**Application version: V1.1 / 1.1.0.**

[Download the Windows release](https://github.com/superdongping/Inper-Batch-CSV-Exporter/releases/tag/v1.1)

A Windows desktop tool for batch export of supported Inper fiber-photometry SQLite recordings to CSV. It runs independently of MATLAB and Fiber Photometry Behavior Analyzer. The packaged EXE includes its Python runtime; a separate Python installation is not required.

V1.1 adds the mouse/fiber/camera application icon, matching window icon, Windows version information and refreshed documentation. **The conversion algorithm is unchanged from V1.0.**

## Quick start

1. Finish acquisition and close software writing to the raw batch.
2. Extract the application folder and double-click **Inper Batch CSV Exporter.exe** (or `START.bat`).
3. Add one or more input batch folders. Each valid recording folder must contain `data.db` and exactly one AVI.
4. Enter a **new, short output path**, such as `G:\InperOut\NewBatch`. It must not already exist or overlap an input folder.
5. Keep **Copy original AVI videos** checked for independent verified copies; uncheck only if you intentionally want references to the original videos.
6. Click **Scan / preview**, check the records, then **Export**. Use the output only when the final `validation_summary.json` reports `status: PASS`.

See [中文完整 instruction](INSTRUCTION_zh-CN.txt), [English quick start](QUICK_START_EN.txt), and [reusable assistant workflow](AGENT_WORKFLOW.txt).

## Data preserved

- Sample-compatible primary CSV: `Time,ROI-1_sig_410,ROI-1_sig_470,...,` with UTF-8 BOM, CRLF and a trailing empty column.
- Complete detailed CSVs under `_details/`: every ROI sample, independent 410/470 nanosecond times, creation times and record IDs, including unmatched tails.
- All nonsignal database tables in metadata; nonempty source event tables also get their own CSVs. These are not automatically converted to Analyzer behavior annotations.
- Batch/animal/recording hierarchy, empty-folder skip list, optional original video copies, animal-folder TXT notes and SHA256 manifests.

The primary CSV uses the 410 timestamp and sample count, pairing wavelengths by sample index. Missing 470 tail samples are blank; extra 470 samples remain in `_details`. No interpolation, filtering, baseline correction, dF/F, behavior inference, group assignment or video synchronization is applied. Preserve the detailed CSVs and check the original independent times when precision matters.

Every saved CSV is read back and checked. Detailed float64 values roundtrip to the original Base64 payload bytes. Copied AVI hashes must match, and source recording files are hashed before/after export. Sources are opened read-only. Existing output folders are refused rather than overwritten or resumed.

## Supported format and known limitations

- Validated Inper SQLite Camera schema, both 410/470 nm per ROI, channel names `ROI-1` through `ROI-N`. Unsupported channels, schemas or invalid values fail explicitly.
- **Windows long paths remain a known limitation in V1.1.** Use a short output root; nested category/animal/recording folders and long filenames may exceed the traditional 260-character path limit when Windows long-path support is disabled. V1.1 does not change system settings or fix this naming behavior. Scan does not yet catch every output-path length failure.
- With extra category levels such as `batch/sensor/animal/recording`, paths are retained, but the manifest's `animal_folder` field may reflect the top category. The tool does not infer animal/group biology. Check IDs, groups and condition labels when creating an Analyzer project.
- Metadata `detailed_csv` uses an absolute path for compatibility with the existing Analyzer. If you move output, correct that link before analysis; an older Analyzer may otherwise fall back to primary shared time. A relative detail path and hash are also recorded.
- No final PASS means incomplete output. Keep failed output for diagnosis, fix the cause and retry to a different new output directory. Do not delete original recordings or database sidecars to bypass an error.
- No new comparison with a vendor GUI export was performed. The decoder is based on the previously checked local vendor reading rules and historical CSV regression, not a bundled vendor library.

## Source use and build

Python 3.10+ with the standard library is sufficient for the source GUI/CLI; Tkinter is needed for the GUI. PyInstaller is needed only to build the Windows executable.

```powershell
python inper_exporter_gui.py
python inper_exporter.py --batch "G:\Raw\Batch" --output "G:\InperOut\NewBatch" --scan-only
python inper_exporter.py --batch "G:\Raw\Batch" --output "G:\InperOut\NewBatch"
python -m unittest discover -s tests -v
.\build.ps1
```

Repeat `--batch` for multiple batches. `--link-videos` references originals instead of copying them. The explicit EXE `--self-test NEW_FOLDER` mode creates only synthetic diagnostic data.

## Version and icon

- **V1.1 / 1.1.0:** new application/window icon, embedded EXE version information and current documentation; export logic unchanged.
- **V1.0 / 1.0.0:** original standalone GUI/CLI and verified primary/detail export pipeline.

The application uses the owner's selected **Mouse fiber photometry converter** image: a mouse with an optical fiber, signal display and conversion folder. The supplied PNG is retained byte-for-byte; only format conversion/downsampling was used for the multi-resolution Windows ICO. `assets/ICON_SOURCE.json` records provenance and the original PNG hash.

Keep recordings, projects, generated output and test artifacts outside source control. No experimental data or vendor executable/DLL belongs in the repository. See `THIRD_PARTY_NOTICES.txt` and `licenses/` for bundled runtime notices. An owner-selected source-code license has not been assigned.
