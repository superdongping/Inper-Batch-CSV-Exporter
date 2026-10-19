"""Synthetic diagnostic only. Never reads research data."""
import base64
import sqlite3
import struct
import time
from contextlib import closing
from pathlib import Path

from inper_exporter import require, write_json


def start_self_test(app, folder):
    root = Path(folder).resolve()
    require(not root.exists(), "Self-test folder must be new")
    source = root / "SYNTHETIC_INPUT" / "2099-01-01 DEMO" / "01 DEMO_ANIMAL" / "recording"
    source.mkdir(parents=True)
    with closing(sqlite3.connect(source / "data.db")) as con, con:
        con.execute("CREATE TABLE ChannelConfig(Id INTEGER PRIMARY KEY,ChannelId INTEGER,LightId INTEGER,ChannelName TEXT,LightName TEXT,Type TEXT,IsDelete INTEGER)")
        for light, wave in enumerate((410, 470)):
            for roi in range(2):
                con.execute("INSERT INTO ChannelConfig VALUES(?,?,?,?,?,?,?)",
                            (light*2+roi+1, roi, light, f"ROI-{roi+1}", f"{wave} nm", "Camera", 0))
            con.execute(f"CREATE TABLE AllChannelRecord{light}(Id INTEGER PRIMARY KEY,Value TEXT,Type INTEGER,CameraTime INTEGER,CreateTime TEXT)")
            for i in range(3):
                value = " ".join(f"{roi}," + base64.b64encode(struct.pack("<d", float(i+roi+light))).decode() for roi in range(2))
                con.execute(f"INSERT INTO AllChannelRecord{light} VALUES(?,?,?,?,?)", (i+1, value, light, i*50000000+light*25000000, "SYNTHETIC"))
    (source / "demo.avi").write_bytes(b"SYNTHETIC VIDEO BYTE COPY TEST - NOT A PLAYABLE AVI")
    app.batches = [str(source.parents[1])]
    app.batch_list.insert("end", app.batches[0])
    app.output.set(str(root / "SYNTHETIC_OUTPUT"))
    deadline = time.monotonic() + 40
    state = {"phase": "scan"}
    app.start_scan()

    def check():
        try:
            require(time.monotonic() < deadline, "Packaged GUI timed out")
            if app.busy:
                app.root.after(100, check)
                return
            if state["phase"] == "scan":
                require(app.status.get().startswith("SCAN PASS"), app.status.get())
                require(len(app.tree.get_children()) == 1, "No scan preview row")
                state["phase"] = "export"
                # Suppress the completion dialog only in this explicit diagnostic mode.
                from unittest.mock import patch
                from tkinter import messagebox
                state["patch"] = patch.object(messagebox, "showinfo")
                state["patch"].start()
                app.start_export()
                app.root.after(100, check)
                return
            require(app.status.get().startswith("COMPLETE"), app.status.get())
            require((root / "SYNTHETIC_OUTPUT" / "validation_summary.json").is_file(), "Missing output")
            state["patch"].stop()
            write_json(root / "packaged_self_test.json", dict(status="PASS", synthetic_only=True,
                gui_scan=True, gui_export=True, video_copy_verified=True, sqlite_available=True,
                independent_python_install_required=False))
            app.root.after(10000, app.root.destroy)
        except Exception as exc:
            write_json(root / "packaged_self_test.json", dict(status="FAILED", error=str(exc)))
            app.root.destroy()
    app.root.after(100, check)
