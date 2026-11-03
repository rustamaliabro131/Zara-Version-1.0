"""packaging/rthook_zara.py — PyInstaller runtime hook for Zara.

Runs before the application code in the frozen build. Two jobs:

1. Point Playwright at the browsers that ship inside the app, when they were
   bundled. Without this, Playwright looks in the per-user cache
   (``%LOCALAPPDATA%\\ms-playwright``) and reports "browser not found" even
   though the browser is sitting right next to the executable.

2. Give ``sys.stdout``/``sys.stderr`` a sink when the windowed build left them
   as ``None``. PyInstaller 6 deliberately matches ``pythonw.exe`` here. Zara
   prints a lot, and a third-party library that writes straight to
   ``sys.stderr`` would otherwise raise on the ``None``. A devnull sink keeps
   those writes harmless; the app's own ``errors.log`` still captures real
   problems, because it opens that file directly.
"""
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _base = Path(sys.executable).resolve().parent

    _browsers = _base / "playwright-browsers"
    if _browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(_browsers))

    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8", errors="replace")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8", errors="replace")
