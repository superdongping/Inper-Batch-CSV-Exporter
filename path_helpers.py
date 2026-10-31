"""Display mapped drives without weakening canonical overlap checks."""
import os
import ntpath
from pathlib import Path
from datetime import datetime


def drive_mappings():
    if os.name != 'nt':
        return {}
    import ctypes
    mappings = {}
    for letter in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        drive = letter + ':'
        size = ctypes.c_ulong(32768)
        buf = ctypes.create_unicode_buffer(size.value)
        if ctypes.windll.mpr.WNetGetConnectionW(drive, buf, ctypes.byref(size)) == 0:
            mappings[drive] = buf.value
    return mappings


def display_path(path, mappings=None):
    # Keep an explicitly selected drive; translate UNC only at display boundary.
    value = os.path.abspath(os.path.expanduser(str(path)))
    mappings = drive_mappings() if mappings is None else mappings
    normalized = ntpath.normpath(value)
    for drive, remote in sorted(mappings.items(), key=lambda x: len(x[1]), reverse=True):
        remote = ntpath.normpath(remote).rstrip('\\')
        if normalized.casefold() == remote.casefold() or normalized.casefold().startswith(remote.casefold() + '\\'):
            return drive + '\\' + normalized[len(remote):].lstrip('\\')
    return value


def overlap(a, b):
    a, b = Path(a).resolve(), Path(b).resolve()
    return a.is_relative_to(b) or b.is_relative_to(a)


def suggested_output(batches, parent=None):
    roots = [Path(p).resolve() for p in batches]
    base = Path(parent) if parent else (Path(display_path(batches[0])).parent if batches else Path.home())
    # If selected parent is within an input, move outside that input.
    while any(base.resolve().is_relative_to(r) for r in roots):
        if base.parent == base:
            base = Path.home()
            if any(base.resolve().is_relative_to(r) for r in roots):
                raise ValueError('Select a narrower input batch or an output on another drive.')
            break
        base = base.parent
    candidate = base / 'Inper_Exports' / datetime.now().strftime('%Y%m%d_%H%M%S')
    suffix = 1
    while candidate.exists() or any(overlap(candidate, r) for r in roots):
        candidate = base / 'Inper_Exports' / (datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + str(suffix))
        suffix += 1
        if suffix > 1000:
            raise ValueError('Choose an output parent outside all inputs.')
    return display_path(candidate)
