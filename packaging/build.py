#!/usr/bin/env python3
"""
packaging/build.py — build ZaraAI with PyInstaller, then ZaraSetup.exe with
Inno Setup.

    python packaging/build.py                 full build (folder + installer)
    python packaging/build.py --skip-browsers  skip the Playwright download
    python packaging/build.py --skip-installer  stop after dist/ZaraAI
    python packaging/build.py --clean           wipe build/ and dist/ first

Run it with the same Python that has Zara's dependencies installed (the one
``python setup.py`` was run with). Steps:

  1. check the Python version
  2. make sure PyInstaller is present
  3. download the Playwright browser into .playwright-browsers/ so browser
     automation works offline (skippable)
  4. write build/version_info.txt (the EXE's Properties → Details tab)
  5. run PyInstaller against packaging/zara.spec  ->  dist/ZaraAI/
  6. find ISCC.exe and compile packaging/installer.iss -> ZaraSetup.exe

Every step prints what it is doing and stops with a clear message on failure,
rather than half-building and leaving you to guess which part broke.
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = ROOT / "packaging"
DIST = ROOT / "dist"
APP_DIR = DIST / "ZaraAI"
BROWSERS_DIR = ROOT / ".playwright-browsers"

APP_NAME = "ZaraAI"
APP_VERSION = "1.0.0"
APP_PUBLISHER = "Zara AI"
APP_DESCRIPTION = "Zara — Sophisticated AI Desktop Assistant"
APP_COPYRIGHT = "Copyright (C) 2026 Zara AI"

MIN_PY = (3, 11)


# ── Console helpers ───────────────────────────────────────────────────────────
def _say(msg: str) -> None:
    print(f"\n\033[1m▶ {msg}\033[0m" if os.name != "nt" else f"\n>> {msg}")


def _ok(msg: str) -> None:
    print(f"  OK  {msg}")


def _warn(msg: str) -> None:
    print(f"  !!  {msg}")


def _die(msg: str, code: int = 1) -> "None":
    print(f"\n  XX  {msg}", file=sys.stderr)
    sys.exit(code)


def _run(args: list[str], **kwargs) -> None:
    """Run a command, echoing it, and stop the build if it fails."""
    print("     " + " ".join(str(a) for a in args))
    try:
        subprocess.run(args, check=True, cwd=str(ROOT), **kwargs)
    except FileNotFoundError:
        _die(f"command not found: {args[0]}")
    except subprocess.CalledProcessError as exc:
        _die(f"command failed (exit {exc.returncode}): {args[0]}")


# ── Steps ─────────────────────────────────────────────────────────────────────
def check_python() -> None:
    _say("Checking Python")
    if sys.version_info[:2] < MIN_PY:
        _die(f"Zara needs Python {MIN_PY[0]}.{MIN_PY[1]} or newer; "
             f"this is {sys.version_info[0]}.{sys.version_info[1]}.")
    _ok(f"Python {sys.version_info[0]}.{sys.version_info[1]} at {sys.executable}")


def ensure_pyinstaller() -> None:
    _say("Checking PyInstaller")
    try:
        import PyInstaller  # noqa: F401
        _ok(f"PyInstaller {PyInstaller.__version__}")
        return
    except ImportError:
        pass
    _warn("PyInstaller is not installed — installing it now")
    _run([sys.executable, "-m", "pip", "install", "--upgrade", "pyinstaller"])


def download_browsers() -> None:
    _say("Downloading the Playwright browser (for offline browser automation)")
    # A frozen app cannot run `playwright install` at runtime (sys.executable is
    # the GUI, not Python), so the browser is fetched here and bundled.
    env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(BROWSERS_DIR))
    try:
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            check=True, cwd=str(ROOT), env=env,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        _warn(f"Could not download the browser ({exc}).")
        _warn("Everything except browser automation will still work. "
              "Install it later with:")
        _warn(f'  set PLAYWRIGHT_BROWSERS_PATH={BROWSERS_DIR} && '
              f'python -m playwright install chromium')
        return
    _ok(f"Browsers in {BROWSERS_DIR}")


def write_version_info() -> None:
    _say("Writing build/version_info.txt")
    out_dir = ROOT / "build"
    out_dir.mkdir(parents=True, exist_ok=True)
    parts = [int(p) for p in APP_VERSION.split(".")] + [0, 0, 0, 0]
    v = tuple(parts[:4])
    text = f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v},
    prodvers={v},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{APP_PUBLISHER}'),
         StringStruct('FileDescription', '{APP_DESCRIPTION}'),
         StringStruct('FileVersion', '{APP_VERSION}'),
         StringStruct('InternalName', '{APP_NAME}'),
         StringStruct('LegalCopyright', '{APP_COPYRIGHT}'),
         StringStruct('OriginalFilename', '{APP_NAME}.exe'),
         StringStruct('ProductName', 'Zara AI Assistant'),
         StringStruct('ProductVersion', '{APP_VERSION}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""
    (out_dir / "version_info.txt").write_text(text, encoding="utf-8")
    _ok("build/version_info.txt")


def run_pyinstaller() -> None:
    _say("Running PyInstaller")
    _run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
        "--log-level", "INFO",
        str(PKG / "zara.spec"),
    ])
    exe = APP_DIR / f"{APP_NAME}.exe"
    if not exe.is_file():
        _die(f"PyInstaller finished but {exe} is missing — see the log above.")
    _ok(f"{exe}")


def find_iscc() -> str | None:
    """Locate Inno Setup's command-line compiler."""
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return found
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"
            / "Inno Setup 6" / "ISCC.exe"),
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return c
    return None


def run_inno() -> None:
    _say("Compiling the installer with Inno Setup")
    iscc = find_iscc()
    if not iscc:
        _warn("Inno Setup (ISCC.exe) was not found.")
        _warn("Install it from https://jrsoftware.org/isdl.php, then re-run "
              "with --skip-browsers to compile only the installer.")
        _warn(f"The app folder is ready at {APP_DIR}")
        return
    _ok(f"ISCC: {iscc}")
    _run([iscc, "/Qp", str(PKG / "installer.iss")])
    setup = DIST / "ZaraSetup.exe"
    if setup.is_file():
        mb = setup.stat().st_size / (1024 * 1024)
        _ok(f"{setup}  ({mb:.1f} MB)")
    else:
        _warn(f"ISCC ran but {setup} was not produced — check its output above.")


# ── Entry point ───────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Build ZaraAI and ZaraSetup.exe")
    parser.add_argument("--skip-browsers", action="store_true",
                        help="do not download the Playwright browser")
    parser.add_argument("--skip-installer", action="store_true",
                        help="stop after dist/ZaraAI (no Inno Setup)")
    parser.add_argument("--clean", action="store_true",
                        help="delete build/ and dist/ before building")
    args = parser.parse_args()

    started = time.time()
    print("=" * 68)
    print(f"  Building {APP_NAME} {APP_VERSION}   ({sys.platform})")
    print("=" * 68)

    if args.clean:
        _say("Cleaning previous output")
        for d in (ROOT / "build", DIST):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
                _ok(f"removed {d}")

    check_python()
    ensure_pyinstaller()
    if not args.skip_browsers:
        download_browsers()
    write_version_info()
    run_pyinstaller()

    if not args.skip_installer:
        run_inno()

    print("\n" + "=" * 68)
    print(f"  Done in {time.time() - started:.0f}s")
    print(f"  App folder : {APP_DIR}")
    print(f"  Installer  : {DIST / 'ZaraSetup.exe'}")
    print("=" * 68)


if __name__ == "__main__":
    main()
