from __future__ import annotations

import platform
from pathlib import Path

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v"}


def pick_recording(initial_dir: str = "") -> str:
    """Open a native local file picker and return the selected recording path."""
    if platform.system().lower() != "windows":
        raise RuntimeError("Native recording browse is currently supported on Windows only")

    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as e:
        raise RuntimeError(f"Windows file picker is unavailable: {e}") from e

    initial = Path(initial_dir).expanduser() if initial_dir else None
    if initial and initial.is_file():
        initial = initial.parent
    if initial and not initial.exists():
        initial = None
    if initial is None:
        videos = Path.home() / "Videos"
        initial = videos if videos.exists() else Path.home()

    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        selected = filedialog.askopenfilename(
            parent=root,
            title="Choose a recording for Postal AutoClip",
            initialdir=str(initial),
            filetypes=[
                ("Video files", "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
                ("All files", "*.*"),
            ],
        )
    finally:
        root.destroy()

    if not selected:
        return ""
    path = Path(selected)
    if not path.exists() or not path.is_file():
        raise RuntimeError("The selected recording could not be found")
    return str(path.resolve())
