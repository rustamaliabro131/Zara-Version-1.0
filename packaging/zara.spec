# -*- mode: python ; coding: utf-8 -*-
"""
packaging/zara.spec — PyInstaller build definition for the Zara AI Assistant.

Build with:
    python packaging/build.py          (recommended — wraps this spec)
    pyinstaller --noconfirm --clean packaging/zara.spec

Output: dist/ZaraAI/ZaraAI.exe  (onedir, windowed)

Why the layout looks unusual
----------------------------
Zara resolves every runtime resource from the folder that holds the executable.
``get_base_dir()`` in main.py returns ``Path(sys.executable).parent`` when frozen,
and ui.py, core/llm_client.py, memory/memory_manager.py, dashboard/server.py and
core/skill_library.py all follow that same rule. Nothing in the app reads
``sys._MEIPASS``.

PyInstaller 6 defaults to putting the executable in the app folder and every
other collected file in an ``_internal`` sub-folder. That would leave the app
looking for ``<app>/config`` while the data sat in ``<app>/_internal/config`` —
so nothing would be found and the app would start with no prompt, no avatar and
no config.

``contents_directory='.'`` restores the flat onedir layout: the executable and
all collected files live side by side, so ``sys._MEIPASS`` equals the app folder
and ``Path(sys.executable).parent`` resolves to where the data actually is. This
one setting is what makes the packaged app find its assets, config and prompt.

Two folders ship as *source*, not frozen bytecode
-------------------------------------------------
``actions/`` and ``plugins/`` are discovered at runtime by scanning the folder
for ``*.py`` and loading each with ``importlib.util.spec_from_file_location``
(see core/action_loader.py and core/plugin_loader.py). A frozen build only ships
imported modules, so these must be added as data or the tool set would be empty.

What is deliberately NOT bundled
--------------------------------
The opt-in heavy engines — ``torch``/``faster-whisper``/``vosk`` (local speech)
and ``kokoro``/``openwakeword`` — plus ``pandas``/``pydub``/``mediapipe``. They
are several hundred MB, are imported lazily behind try/except at the point of
use, and are not needed for the default experience (the Live session does speech
server-side and the default TTS is edge-tts). They are listed in ``excludes``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

# ── Paths ─────────────────────────────────────────────────────────────────────
# SPECPATH is injected by PyInstaller and points at this file's directory. The
# fallback lets the file be read by tools that exec it outside a build.
try:
    ROOT = Path(SPECPATH).resolve().parent          # noqa: F821
except NameError:                                   # pragma: no cover
    ROOT = Path(__file__).resolve().parent.parent   # noqa: F821

APP_NAME = "ZaraAI"

# ── Data helpers ──────────────────────────────────────────────────────────────
_SKIP_DIRS = {
    "__pycache__", ".git", ".github", ".claude-plugin", ".mypy_cache",
    ".pytest_cache", ".idea", ".vscode", ".ipynb_checkpoints", ".ruff_cache",
}
_SKIP_FILES = {"desktop.ini", "Thumbs.db", ".DS_Store", ".gitkeep"}
_SKIP_SUFFIX = {".pyc", ".pyo", ".pyi", ".c", ".h", ".cpp", ".pdb", ".exp"}


def _tree(src: Path, dest: str, skip: set[str] | None = None) -> list[tuple[str, str]]:
    """Every file under *src* as (absolute_path, destination_dir) pairs.

    PyInstaller copies a directory's *contents* into the destination, so
    ``_tree(root/"assists", "assists")`` places ``assists/GIF/idle.gif`` at
    ``<app>/assists/GIF/idle.gif``. Cache and editor junk is dropped so the
    bundle stays clean and small.
    """
    out: list[tuple[str, str]] = []
    if not src.is_dir():
        return out
    skip = skip or set()
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if any(part in _SKIP_DIRS or part in skip for part in rel.parts):
            continue
        if path.name in _SKIP_FILES or path.suffix.lower() in _SKIP_SUFFIX:
            continue
        parent = str(rel.parent).replace("\\", "/")
        dest_dir = dest if parent in (".", "") else f"{dest}/{parent}"
        out.append((str(path), dest_dir))
    return out


# ── Bundled data ──────────────────────────────────────────────────────────────
datas: list[tuple[str, str]] = []

# Avatar GIFs and clips — resolved from <app>/assists at runtime.
datas += _tree(ROOT / "assists", "assists")

# Icons. api_keys.json is intentionally absent: it holds the user's API key, is
# git-ignored, and the app creates it on first run.
for _name in ("zara.png", "zara.ico"):
    _icon = ROOT / "config" / _name
    if _icon.is_file():
        datas.append((str(_icon), "config"))

# Data files that live inside the `core` package (the code itself is bytecode).
for _name in ("face_model.obj", "prompt.txt"):
    _f = ROOT / "core" / _name
    if _f.is_file():
        datas.append((str(_f), "core"))

# Remote dashboard's web UI.
datas += _tree(ROOT / "dashboard" / "static", "dashboard/static")

# Dynamically-discovered tools — must ship as source (see header).
datas += _tree(ROOT / "actions", "actions")
datas += _tree(ROOT / "plugins", "plugins")

# WhatsApp call skill + browser-automation skills (statically imported), and the
# two architecture notes. The research library is added separately, trimmed.
datas += _tree(ROOT / "skills", "skills", skip={"AI-Research-SKILLs"})

# Icon source portrait — used to rebuild the icon if it is ever missing.
_icon_src = ROOT / "futuristic_sci_fi_ai_hologram_female_avatar_portrait_of_zara_cyberpunk_jarvis"
datas += _tree(_icon_src, _icon_src.name)

# Research skill library. core/skill_library.py indexes every SKILL.md and skips
# the non-skill top-level folders itself, so they are dropped here too rather
# than shipped unread (demos + docs + video-promo alone are ~16 MB).
_lib = ROOT / "skills" / "AI-Research-SKILLs"
_LIB_SKIP_TOP = {
    "demos", "docs", "dev_data", "packages", "scripts", "video-promo",
    "anthropic_official_docs", ".github", ".claude-plugin",
}
if _lib.is_dir():
    for _child in sorted(_lib.iterdir()):
        if _child.name in _LIB_SKIP_TOP:
            continue
        if _child.is_dir():
            datas += _tree(_child, f"skills/AI-Research-SKILLs/{_child.name}")
        elif _child.suffix.lower() == ".md":
            datas.append((str(_child), "skills/AI-Research-SKILLs"))

# Docs.
for _name in ("readme.md", "LICENSE"):
    _f = ROOT / _name
    if _f.is_file():
        datas.append((str(_f), "."))

# Playwright browsers, when build.py downloaded them. Runtime download does not
# work in a frozen build (sys.executable is the GUI, not Python), so bundling is
# how browser automation keeps working offline. rthook_zara.py points Playwright
# at this folder.
_browsers = ROOT / ".playwright-browsers"
if _browsers.is_dir():
    datas += _tree(_browsers, "playwright-browsers")
    print(f"[zara.spec] Bundling Playwright browsers from {_browsers}")

# Package metadata some libraries read via importlib.metadata at runtime.
for _pkg in ("playwright", "google-genai", "uvicorn", "fastapi", "PyQt6"):
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

# ── Hidden imports ────────────────────────────────────────────────────────────
hiddenimports: list[str] = [
    # Local packages — some are namespace packages (no __init__.py) or are only
    # reached through the runtime file scanners.
    "actions", "plugins", "skills", "engine", "memory", "dashboard", "config",
    "core", "gui",
    "actions.screen_processor", "actions.system_monitor", "actions.proactive",
    "actions.background_monitor", "actions.web_search", "actions.browser_automation",
    "actions.browser_control", "actions.file_processor", "actions.flight_finder",
    "actions.code_helper", "actions.dev_agent", "actions.reminder",
    "actions.weather_report", "actions.send_message", "actions.open_app",
    "actions.desktop", "actions.computer_control", "actions.computer_settings",
    "actions.youtube_video", "actions.research_topic", "actions.browse_skills",
    "actions.write_document", "actions.game_updater",
    "engine.browser_core", "engine.human_browser", "engine.browser_vision",
    "skills.whatsapp_call_assistant",
    "skills.browser_automation", "skills.browser_automation.upwork_bidder",
    "skills.browser_automation.amazon_kdp_publisher",
    "skills.browser_automation.fiverr_gig_creator",
    "skills.browser_automation.facebook_poster",
    "skills.browser_automation.daraz_shopper",
    # Qt — the HUD is PyQt6.
    "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
    # Gemini Live.
    "google.genai", "google.genai.types",
    # Browser automation.
    "playwright", "playwright.sync_api", "playwright.async_api", "playwright._impl",
    # Imaging / audio / system.
    "PIL", "PIL.Image", "PIL.ImageSequence", "PIL.ImageTk", "PIL.ImageDraw",
    "numpy", "sounddevice", "cv2", "mss", "psutil", "miniaudio",
    # Web / documents.
    "requests", "bs4", "ddgs", "duckduckgo_search", "youtube_transcript_api",
    "pptx", "docx", "PyPDF2", "pdfplumber", "openpyxl", "send2trash",
    # Input control.
    "pyautogui", "pyperclip", "pygetwindow", "pyttsx3",
    # Remote dashboard.
    "fastapi", "uvicorn", "cryptography", "multipart", "qrcode",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
    # Plugin extras.
    "googleapiclient", "google_auth_oauthlib", "tinytuya", "paho.mqtt", "pynvml",
    # Light, network TTS.
    "edge_tts",
    # tkinter — gui/avatar.py's fallback avatar.
    "tkinter", "tkinter.ttk", "tkinter.filedialog", "tkinter.simpledialog",
    "certifi",
]

# Windows-only OS control.
if sys.platform == "win32":
    hiddenimports += [
        "comtypes", "pycaw", "win10toast", "pywinauto", "wmi",
        "win32com", "win32com.client", "pythoncom", "win32api", "win32con",
        "winreg",
    ]

try:
    hiddenimports += collect_submodules("uvicorn")
except Exception:
    pass

# ── Excludes ──────────────────────────────────────────────────────────────────
excludes: list[str] = [
    # Opt-in heavy engines, imported lazily and never on the default path.
    "torch", "torchvision", "torchaudio", "faster_whisper", "vosk", "kokoro",
    "openwakeword",
    # Optional document/media extras.
    "pandas", "pydub", "mediapipe", "matplotlib", "scipy", "sklearn",
    # Dev/test tooling.
    "IPython", "notebook", "jupyter", "pytest", "_pytest", "setuptools", "pip",
    # Other Qt bindings and unused Qt modules (keeps the bundle much smaller).
    "PyQt5", "PySide2", "PySide6",
    "PyQt6.QtWebEngineCore", "PyQt6.QtWebEngineWidgets", "PyQt6.QtWebEngineQuick",
    "PyQt6.QtQml", "PyQt6.QtQuick", "PyQt6.QtQuick3D", "PyQt6.QtQuickWidgets",
    "PyQt6.Qt3DCore", "PyQt6.Qt3DRender", "PyQt6.Qt3DAnimation",
    "PyQt6.QtCharts", "PyQt6.QtDataVisualization", "PyQt6.QtDesigner",
    "PyQt6.QtHelp", "PyQt6.QtPdf", "PyQt6.QtPdfWidgets", "PyQt6.QtSql",
    "PyQt6.QtTest", "PyQt6.QtBluetooth", "PyQt6.QtNfc", "PyQt6.QtSerialPort",
    "PyQt6.QtSensors", "PyQt6.QtWebSockets", "PyQt6.QtWebChannel",
    "PyQt6.QtNetworkAuth", "PyQt6.QtPositioning", "PyQt6.QtRemoteObjects",
]

# ── Build ─────────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "packaging" / "rthook_zara.py")],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

_version_file = ROOT / "build" / "version_info.txt"

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,                      # UPX corrupts Qt/Playwright DLLs
    console=False,                  # windowed: no black console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "config" / "zara.ico"),
    version=str(_version_file) if _version_file.is_file() else None,
    contents_directory=".",         # flat onedir — see the module docstring
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_NAME,
)

print(f"[zara.spec] data files: {len(datas)}   hidden imports: {len(hiddenimports)}")
