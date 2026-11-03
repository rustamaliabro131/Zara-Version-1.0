# AGENTS.md

Repository-specific notes for AI agents working on Zara.

## What this is

Zara is a voice AI desktop assistant: a PyQt6 HUD, a Gemini Live session,
Playwright browser automation, and a folder-scanned tool system. Entry point is
`main.py`.

## Commands

```bash
python main.py                       # run
python -m py_compile main.py ui.py   # syntax check (no test suite)
python packaging/build.py            # build Windows installer (Windows only)
```

There is no automated test suite. Verification is `py_compile` plus targeted
simulation scripts.

## Architecture facts that are easy to get wrong

**Resource resolution.** `main.py:get_base_dir()` returns
`Path(sys.executable).parent` when frozen, and `ui.py`, `core/llm_client.py`,
`memory/memory_manager.py`, `dashboard/server.py` and `core/skill_library.py`
all follow it. Nothing reads `sys._MEIPASS`. So the packaged app expects its
data *beside the exe* — `packaging/zara.spec` sets `contents_directory="."` for
exactly this reason.

**Runtime-discovered tools.** `core/action_loader.py` and
`core/plugin_loader.py` scan `actions/` and `plugins/` for `*.py` and load each
with `importlib.util.spec_from_file_location`. Those folders must ship as
**source** in any build, not just as frozen bytecode.

**Writable paths.** The app writes `config/api_keys.json`,
`memory/long_term.json`, `config/errors.log` and `uploads/` inside its own
folder. Anything that installs or relocates it must keep those writable.

**Startup handshake.** `main.py` warms heavy subsystems on a daemon thread
(`initialize_systems`) and hands the HUD from INITIALISING to Idle through
`_StartupCoordinator`. Two invariants:
- The handshake lives in a `finally` block — it must run even if warm-up aborts.
- The session runner's first real state beats the worker's Idle. While the
  first-run setup modal is up (`ui._win._ready is False`), the worker must not
  publish Idle; `_on_setup_done` owns that transition.

`ZARA_INIT_TIMEOUT` (default 25s) bounds the whole warm-up.

**STT/TTS.** No local STT at startup — the Live session does recognition
server-side. Default TTS is edge-tts (network). Local engines (`torch`,
`faster-whisper`, `vosk`, `kokoro`, `openwakeword`) are opt-in, lazily imported
behind try/except, and deliberately excluded from the packaged build.

## Packaging

`packaging/` holds the PyInstaller spec, Inno Setup script and build driver.
See `packaging/README.md`. Key point: the bundle is `--onedir --windowed` with a
flat layout. `package.bat` is the one-click Windows entry point.

## Conventions

- `config/api_keys.json` holds every credential and is git-ignored. Never
  commit it; never add another secrets file.
- Comments explain *why* (a non-obvious invariant, a workaround), not *what*.
  Match that style.
- Branch workflow on this repo: commit and push to the working branch; do not
  open a PR unless asked.
