"""Desktop entry point. Worker threads never mutate Tk widgets."""
import os
import sys
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from inper_exporter import VERSION, run_export, scan


class ExporterApp:
    def __init__(self, root):
        self.root = root
        self.busy = False
        self.messages = queue.Queue()
        self.batches = []
        self.output = tk.StringVar()
        self.copy_videos = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value="Add batch folders, choose a NEW output folder, then Scan.")
        root.title(f"Inper Batch CSV Exporter {VERSION}")
        asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        icon = asset_root / "assets" / "inper-exporter.ico"
        if icon.is_file():
            root.iconbitmap(str(icon))
        root.geometry("1000x760")
        root.minsize(850, 620)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame = ttk.Frame(root, padding=12)
        frame.grid(sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(7, weight=1)
        frame.rowconfigure(9, weight=1)
        ttk.Label(frame, text="Inper → CSV", font=("Segoe UI", 17, "bold")).grid(row=0, sticky="w")
        ttk.Label(frame, text="Read-only sources · Sample-compatible CSV + full detailed CSV · No overwrite").grid(row=1, sticky="w", pady=(0, 8))
        batch_frame = ttk.LabelFrame(frame, text="1. Input batch folders (each contains animal/session/data.db)", padding=6)
        batch_frame.grid(row=2, sticky="ew")
        batch_frame.columnconfigure(0, weight=1)
        self.batch_list = tk.Listbox(batch_frame, height=4, selectmode="extended", exportselection=False)
        self.batch_list.grid(row=0, column=0, rowspan=2, sticky="ew")
        self.add_button = ttk.Button(batch_frame, text="Add batch…", command=self.add_batch)
        self.add_button.grid(row=0, column=1, padx=6)
        self.remove_button = ttk.Button(batch_frame, text="Remove selected", command=self.remove_batches)
        self.remove_button.grid(row=1, column=1, padx=6)
        out_frame = ttk.LabelFrame(frame, text="2. Output: enter a NEW folder name (existing folders are refused)", padding=6)
        out_frame.grid(row=3, sticky="ew", pady=8)
        out_frame.columnconfigure(0, weight=1)
        self.output_entry = ttk.Entry(out_frame, textvariable=self.output)
        self.output_entry.grid(row=0, column=0, sticky="ew")
        self.output_button = ttk.Button(out_frame, text="Choose parent…", command=self.choose_output)
        self.output_button.grid(row=0, column=1, padx=6)
        self.video_check = ttk.Checkbutton(frame, text="Copy original AVI videos and verify SHA256 (recommended; uses additional disk space)", variable=self.copy_videos)
        self.video_check.grid(row=4, sticky="w")
        buttons = ttk.Frame(frame)
        buttons.grid(row=5, sticky="ew", pady=8)
        self.scan_button = ttk.Button(buttons, text="3. Scan / preview (read-only)", command=self.start_scan)
        self.scan_button.pack(side="left")
        self.export_button = ttk.Button(buttons, text="4. Export", command=self.start_export)
        self.export_button.pack(side="left", padx=8)
        self.open_button = ttk.Button(buttons, text="Open output", command=self.open_output)
        self.open_button.pack(side="right")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.grid(row=6, sticky="ew", pady=(0, 5))
        self.tree = ttk.Treeview(frame, columns=("batch", "animal", "session", "target"), show="headings", height=7)
        for col, label, width in (("batch", "Batch", 220), ("animal", "Animal folder", 120),
                                  ("session", "Recording", 130), ("target", "Output relative folder", 380)):
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width)
        self.tree.grid(row=7, sticky="nsew")
        ttk.Label(frame, textvariable=self.status, wraplength=920).grid(row=8, sticky="w", pady=6)
        self.log = tk.Text(frame, height=7, wrap="word", state="disabled", font=("Consolas", 9))
        self.log.grid(row=9, sticky="nsew")
        ttk.Label(frame, text="Time = 410 nm sample time; no interpolation. Full independent times/tails are in _details.\nDo not convert while acquisition is running. A FAILED.json means the output is incomplete.").grid(row=10, sticky="w", pady=(8, 0))
        self.controls = [self.add_button, self.remove_button, self.output_entry, self.output_button,
                         self.video_check, self.scan_button, self.export_button, self.open_button, self.batch_list]
        root.after(100, self.poll)

    def add_batch(self):
        folder = filedialog.askdirectory(title="Choose one batch folder (containing animal subfolders)")
        if folder and str(Path(folder).resolve()) not in self.batches:
            self.batches.append(str(Path(folder).resolve()))
            self.batch_list.insert("end", self.batches[-1])

    def remove_batches(self):
        for index in reversed(self.batch_list.curselection()):
            del self.batches[index]
            self.batch_list.delete(index)

    def choose_output(self):
        parent = filedialog.askdirectory(title="Choose output PARENT folder")
        if parent:
            self.output.set(str(Path(parent) / "Inper_Export_NewBatch"))

    def set_busy(self, value):
        self.busy = value
        for widget in self.controls:
            widget.configure(state="disabled" if value else "normal")
        if value:
            self.progress.start(15)
        else:
            self.progress.stop()

    def parameters(self):
        if not self.batches or not self.output.get().strip():
            messagebox.showerror("Missing input", "Add at least one batch and enter a new output folder.")
            return None
        return list(self.batches), self.output.get().strip(), self.copy_videos.get()

    def worker(self, export):
        params = self.parameters()
        if params is None or self.busy:
            return
        batches, output, copy = params
        self.set_busy(True)
        self.status.set("Exporting and verifying…" if export else "Scanning databases (read-only)…")

        def task():
            try:
                log = lambda text: self.messages.put(("log", text))
                if export:
                    result = run_export(batches, output, copy, log)
                    self.messages.put(("exported", (output, len(result))))
                else:
                    jobs, skipped, warnings = scan(batches, output, log)
                    self.messages.put(("scanned", (jobs, skipped, warnings)))
            except Exception as exc:
                self.messages.put(("error", str(exc)))
            finally:
                self.messages.put(("finished", None))
        threading.Thread(target=task, daemon=True).start()

    def start_scan(self):
        self.worker(False)

    def start_export(self):
        self.worker(True)

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        try:
            while True:
                kind, data = self.messages.get_nowait()
                if kind == "log":
                    self.append_log(data)
                elif kind == "scanned":
                    jobs, skipped, warnings = data
                    self.tree.delete(*self.tree.get_children())
                    for job in jobs:
                        self.tree.insert("", "end", values=(job.batch.name, job.mouse.name, job.session.name, str(job.target)))
                    for text in warnings:
                        self.append_log("WARNING: " + text)
                    self.status.set(f"SCAN PASS: {len(jobs)} recordings, {len(skipped)} empty folders, {len(warnings)} warnings. No output written.")
                elif kind == "exported":
                    output, count = data
                    self.status.set(f"COMPLETE: {count} recordings. {output}")
                    messagebox.showinfo("Export complete", f"{count} recordings exported and verified.\n{output}\n\nCheck validation_summary.json: status PASS.")
                elif kind == "error":
                    self.status.set("FAILED: " + data)
                    self.append_log("ERROR: " + data)
                    messagebox.showerror("Export / scan failed", data + "\n\nExisting inputs are not overwritten. If a partial output was created, use a different new folder after fixing the issue.")
                elif kind == "finished":
                    self.set_busy(False)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def open_output(self):
        path = Path(self.output.get())
        if self.output.get() and path.is_dir():
            os.startfile(str(path.resolve()))

    def close(self):
        if self.busy:
            messagebox.showinfo("Please wait", "A scan/export is running. Wait for completion to avoid an incomplete output.")
        else:
            self.root.destroy()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Inper Batch CSV Exporter desktop application")
    parser.add_argument("--self-test", metavar="NEW_FOLDER", help="Run packaged synthetic GUI/export check")
    args = parser.parse_args()
    root = tk.Tk()
    app = ExporterApp(root)
    if args.self_test:
        from packaged_self_test import start_self_test
        start_self_test(app, args.self_test)
    root.mainloop()


if __name__ == "__main__":
    main()
