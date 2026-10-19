import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

from inper_exporter_gui import ExporterApp
from test_exporter import make_record


class GuiTests(unittest.TestCase):
    def test_scan_and_export_worker_and_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk()
            root.withdraw()
            try:
                app = ExporterApp(root)
                batch = Path(folder) / "2026-10-13 Task"
                make_record(batch)
                app.batches = [str(batch)]
                app.output.set(str(Path(folder) / "output"))
                self.assertTrue(app.copy_videos.get())
                app.start_scan()
                self.wait(root, app)
                self.assertTrue(app.status.get().startswith("SCAN PASS"), app.status.get())
                self.assertEqual(len(app.tree.get_children()), 1)
                self.assertFalse(Path(app.output.get()).exists())
                with patch("inper_exporter_gui.messagebox.showinfo") as info:
                    app.start_export()
                    self.wait(root, app)
                    self.assertTrue(app.status.get().startswith("COMPLETE"), app.status.get())
                    info.assert_called_once()
                self.assertTrue((Path(app.output.get()) / "validation_summary.json").is_file())
                self.assertEqual(str(app.scan_button.cget("state")), "normal")
                with patch("inper_exporter_gui.messagebox.showerror") as error:
                    app.start_export()
                    self.wait(root, app)
                    self.assertTrue(app.status.get().startswith("FAILED"))
                    error.assert_called_once()
            finally:
                root.destroy()

    @staticmethod
    def wait(root, app):
        deadline = time.monotonic() + 15
        while app.busy and time.monotonic() < deadline:
            root.update()
            time.sleep(.02)
        if app.busy:
            raise AssertionError("GUI worker timed out")


if __name__ == "__main__":
    unittest.main()
