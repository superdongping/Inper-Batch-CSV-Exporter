# Linked data and portable projects

Exporter 1.2.0 + Analyzer 1.3.0. Released as Exporter v1.2 and Analyzer v1.3.

## Everyday workflow
1. Run the updated Exporter EXE. Add one or more batches; choose a NEW, short output directory. Scan then Export. Wait for PASS.
2. Export includes dataset.json with stable recording IDs, relative file references and identity hints. Source acquisition files are never edited.
3. Click Create Analyzer project (requires MATLAB and the updated Analyzer), or launch_analyzer in MATLAB and select New project. Select the folder containing dataset.json.
4. Review suggested animal IDs and sensor-based group names. Groups remain editable. Enter ROI names and behavior names. In the identity table, verify AnimalID and condition, then confirm rows. Unknown or unchecked identities are excluded. No timestamp is accepted as a confirmed animal automatically.
5. Remember identities writes dataset_identity.json alongside the exported dataset (not into raw source data). This is explicit, optional, backed up on replacement, and reused by future projects. Groups are proposed again for review. Read-only datasets can use project-only identities.
6. Save events in the viewer before copying or packaging. Unsaved viewer changes are not part of a project copy.

## Three project operations
- Copy project: choose a NEW folder name. Copies project configuration and saved events; shares CSV/video. Results and historical backups are not copied. Each project's subsequent events are independent.
- Relocate data: select the new dataset root. Recording IDs and hashes verify matching files; all mappings are checked before saving. No filename-only guessing. Legacy projects without hashes require explicit confirmation if originals are unavailable. Preserve the relative data tree for legacy relocation.
- Portable package: choose a NEW folder name. Produces that folder plus a ZIP containing project.mat, events and all referenced recording data/videos, including excluded sessions. Unzip anywhere and Open project. Historical analysis outputs are omitted. Dataset provenance in metadata is retained, but runtime references resolve within the package.

Move the ENTIRE project folder, not project.mat alone. Events are separate files in events/. A missing events directory is an error, never interpreted as no annotations.

## Portability and scientific integrity
- The saved project retains absolute fallbacks plus relative data references. Whole-tree moves resolve automatically. Separate data moves use Relocate data; offline projects can open in the manager for repair.
- Detailed wavelength CSVs resolve relative to their metadata or dataset before trying legacy absolute references. Missing/changed expected details cause an explicit error. There is no silent fallback to shared 410 time.
- Original time precision, wavelength samples, ROI mapping, event times, sync offsets and analysis settings are preserved. Copying does not infer or re-confirm synchronization.
- Recording IDs distinguish repeated recordings; repeated exports of the same batch identity/content retain IDs. Renaming source batches before re-export changes identity and should be reviewed. Animal names reused for different real animals must be disambiguated during confirmation; the program cannot infer biological identity.
- Linked external videos are supported, but those files must be available to build a portable package.
- Old exports remain importable through the legacy discovery rules. They do not need to be re-exported. Save configuration from the new Analyzer once while sources are available to capture relative paths and hashes.
- Creating projects and verified portable packages hashes video files and can take time on large datasets. Packaging uses additional disk space. Partially failed copies are marked COPY_FAILED.txt and refused on load; partial ZIPs have .partial.zip suffix.

## Launch
Exporter: Inper Batch CSV Exporter.exe (Python is not required).
Analyzer: set MATLAB Current Folder to this updated Analyzer folder; run launch_analyzer. Existing research project folders can be opened directly. Do not open the older code directory accidentally.

## Scope
This build does not change signal decoding, filtering, normalization, animal/trial weighting or behavior definitions. No existing research project is automatically migrated on disk. Source and release packages are available in the two GitHub repositories.
