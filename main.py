"""
main.py
─────────────────────────────────────────────
Entry point for the AI Driver Drowsiness Detection System.

Startup sequence
────────────────
1. Check Python version
2. Verify critical dependencies (non-fatal warnings for optional ones)
3. Ensure required project directories exist
4. Launch the CustomTkinter GUI
"""

import sys
import os
import importlib
import logging
from pathlib import Path

# ── Minimum Python version ────────────────────────────────────────────────
if sys.version_info < (3, 9):
    print("ERROR: Python 3.9+ is required. Current:", sys.version)
    sys.exit(1)

# ── Logging bootstrap (before importing modules) ──────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_log = logging.getLogger("Main")

# ── Dependency check ──────────────────────────────────────────────────────
_REQUIRED = {
    "cv2":           "opencv-python",
    "mediapipe":     "mediapipe",
    "numpy":         "numpy",
    "customtkinter": "customtkinter",
    "PIL":           "Pillow",
}
_OPTIONAL = {
    "serial":        "pyserial        (Arduino support)",
    "pyttsx3":       "pyttsx3         (audio alerts)",
    "matplotlib":    "matplotlib      (EAR graph)",
    "openpyxl":      "openpyxl        (Excel export)",
    "scipy":         "scipy           (advanced signal processing)",
}

missing_required = []
for mod, pkg in _REQUIRED.items():
    try:
        importlib.import_module(mod)
    except ImportError:
        missing_required.append(pkg)

if missing_required:
    print("\n" + "=" * 60)
    print("MISSING REQUIRED PACKAGES — install with:")
    print("  pip install " + " ".join(missing_required))
    print("=" * 60 + "\n")
    sys.exit(1)

for mod, pkg in _OPTIONAL.items():
    try:
        importlib.import_module(mod)
    except ImportError:
        _log.warning("Optional package not installed: %s", pkg)

_log.info("All required dependencies present")

# ── Project directory guard ───────────────────────────────────────────────
_here = Path(__file__).parent
for _sub in ("data", "logs", "assets", "models"):
    (_here / _sub).mkdir(exist_ok=True)

# ── Launch GUI ────────────────────────────────────────────────────────────
def main() -> None:
    _log.info("Starting AI Driver Drowsiness Detection System …")
    try:
        # Import here so import errors are caught cleanly
        from ui import MainApp
        app = MainApp()
        app.mainloop()
    except KeyboardInterrupt:
        _log.info("Interrupted by user — exiting")
    except Exception as exc:
        _log.critical("Fatal error: %s", exc, exc_info=True)
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Fatal Error",
                f"The application encountered a critical error:\n\n{exc}\n\n"
                "Check the terminal for the full traceback.",
            )
            root.destroy()
        except Exception:    # noqa: BLE001
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
