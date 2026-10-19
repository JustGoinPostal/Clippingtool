from __future__ import annotations

import json
import logging
import os
import threading
import time
import webbrowser
from pathlib import Path

from .paths import APP_HOME, LOG_DIR, PROGRAM_ROOT, ensure_app_home

SETUP_STATE = APP_HOME / "setup.json"


def _log_setup() -> Path:
    ensure_app_home()
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / "desktop.log"
    logging.basicConfig(
        filename=str(path),
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    return path


def _setup_complete() -> bool:
    if not SETUP_STATE.exists():
        return False
    try:
        payload = json.loads(SETUP_STATE.read_text(encoding="utf-8"))
        return bool(payload.get("completed"))
    except Exception:
        return False


def _save_setup_state(watch: Path, output: Path) -> None:
    SETUP_STATE.write_text(json.dumps({
        "completed": True,
        "version": 1,
        "data_root": str(APP_HOME),
        "watch_folder": str(watch),
        "output_folder": str(output),
        "completed_at": time.time(),
    }, indent=2), encoding="utf-8")


def _run_first_setup() -> bool:
    if _setup_complete():
        return True
    from .config import load_settings, save_settings
    settings = load_settings()

    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except Exception as exc:
        logging.exception("First-run UI unavailable: %s", exc)
        _save_setup_state(settings.watch_path, settings.output_path)
        return True

    result = {"continue": False}
    root = tk.Tk()
    root.title("Postal AutoClip Beta — First Run")
    root.geometry("760x520")
    root.minsize(700, 500)

    watch_var = tk.StringVar(value=str(settings.watch_path))
    output_var = tk.StringVar(value=str(settings.output_path))
    auto_var = tk.BooleanVar(value=bool(settings.auto_process_new_files))

    outer = tk.Frame(root, padx=28, pady=24)
    outer.pack(fill="both", expand=True)
    tk.Label(outer, text="Postal AutoClip", font=("Segoe UI", 22, "bold")).pack(anchor="w")
    tk.Label(
        outer,
        text="Your private AutoClip state stays in Windows AppData. Large recordings and renders can live on any drive you choose.",
        font=("Segoe UI", 10), wraplength=690, justify="left",
    ).pack(anchor="w", pady=(4, 18))

    tk.Label(outer, text="Private app data", font=("Segoe UI", 10, "bold")).pack(anchor="w")
    data_box = tk.Entry(outer, font=("Consolas", 9))
    data_box.insert(0, str(APP_HOME))
    data_box.configure(state="readonly")
    data_box.pack(fill="x", pady=(4, 14))

    def folder_row(title: str, variable: tk.StringVar, help_text: str):
        tk.Label(outer, text=title, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = tk.Frame(outer)
        row.pack(fill="x", pady=(4, 2))
        entry = tk.Entry(row, textvariable=variable, font=("Consolas", 9))
        entry.pack(side="left", fill="x", expand=True)
        def browse():
            current = Path(variable.get()).expanduser()
            initial = current if current.exists() and current.is_dir() else Path.home()
            chosen = filedialog.askdirectory(parent=root, initialdir=str(initial), title=title)
            if chosen:
                variable.set(str(Path(chosen).resolve()))
        tk.Button(row, text="Browse…", command=browse, width=12).pack(side="left", padx=(8, 0))
        tk.Label(outer, text=help_text, font=("Segoe UI", 9), fg="#555555", wraplength=690, justify="left").pack(anchor="w", pady=(0, 12))

    folder_row(
        "OBS recording folder",
        watch_var,
        "AutoClip watches this folder for new VODs. This can be D:\\, E:\\, a large SSD, or any local folder.",
    )
    folder_row(
        "Rendered clip folder",
        output_var,
        "Finished Shorts/Reels/TikToks are written here. Put this on a larger drive if you do not want media consuming your system drive.",
    )

    tk.Checkbutton(outer, text="Automatically process new recordings", variable=auto_var, font=("Segoe UI", 10)).pack(anchor="w", pady=(2, 16))

    tk.Label(
        outer,
        text="Database, learning history, OAuth tokens, benchmark labels, logs, covers, and model cache remain isolated under AppData. Uninstalling AutoClip will not delete that creator data.",
        font=("Segoe UI", 9), fg="#444444", wraplength=690, justify="left",
    ).pack(anchor="w", pady=(0, 18))

    buttons = tk.Frame(outer)
    buttons.pack(fill="x", side="bottom")

    def save_and_continue():
        try:
            watch = Path(watch_var.get()).expanduser().resolve()
            output = Path(output_var.get()).expanduser().resolve()
            if not watch.exists() or not watch.is_dir():
                raise ValueError("Choose an existing OBS recording folder.")
            output.mkdir(parents=True, exist_ok=True)
            save_settings({
                "watch_folder": str(watch),
                "output_folder": str(output),
                "cache_folder": str(APP_HOME / "data" / "cache"),
                "auto_process_new_files": bool(auto_var.get()),
            })
            _save_setup_state(watch, output)
            result["continue"] = True
            root.destroy()
        except Exception as exc:
            messagebox.showerror("Postal AutoClip", str(exc), parent=root)

    def cancel():
        result["continue"] = False
        root.destroy()

    tk.Button(buttons, text="Exit", command=cancel, width=12).pack(side="right")
    tk.Button(buttons, text="Save & Open AutoClip", command=save_and_continue, width=22).pack(side="right", padx=(0, 8))
    root.protocol("WM_DELETE_WINDOW", cancel)
    root.mainloop()
    return bool(result["continue"])


def _open_dashboard() -> None:
    time.sleep(1.25)
    try:
        webbrowser.open("http://127.0.0.1:8787")
    except Exception:
        logging.exception("Could not open dashboard")


def run() -> None:
    log_path = _log_setup()
    logging.info("Starting Postal AutoClip; program=%s data=%s", PROGRAM_ROOT, APP_HOME)
    try:
        if not _run_first_setup():
            return
        threading.Thread(target=_open_dashboard, daemon=True).start()
        import uvicorn
        from .api import app
        uvicorn.run(app, host="127.0.0.1", port=8787, log_level="info")
    except Exception as exc:
        logging.exception("Postal AutoClip failed to start")
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk(); root.withdraw()
            messagebox.showerror(
                "Postal AutoClip failed to start",
                f"{type(exc).__name__}: {exc}\n\nLog: {log_path}",
                parent=root,
            )
            root.destroy()
        except Exception:
            pass
        raise


if __name__ == "__main__":
    run()
