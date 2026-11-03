# Packaging Zara into a Windows installer

This folder builds Zara into a standalone Windows application and a single
installer, `ZaraSetup.exe`. End users get a normal Windows app — Start Menu
entry, desktop icon, an uninstaller — with no Python required.

```
packaging/
├── zara.spec              PyInstaller build definition
├── rthook_zara.py         runtime hook (Playwright browsers, stdout sink)
├── installer.iss          Inno Setup script
├── BEFORE_INSTALL.txt     shown by the installer wizard
└── build.py               runs both steps in sequence
package.bat                double-click wrapper for build.py
```

## What you get

| Output | Description |
| --- | --- |
| `dist/ZaraAI/` | The app folder: `ZaraAI.exe` plus everything it needs |
| `dist/ZaraSetup.exe` | The installer to hand to users |

## One-time setup

1. **Python 3.11–3.13**, 64-bit, on PATH. Install Zara's dependencies first:
   ```
   python setup.py
   ```
2. **Inno Setup 6.3 or newer** — https://jrsoftware.org/isdl.php
   (needed for the `x64compatible` architecture settings). Install it to the
   default location; `build.py` finds `ISCC.exe` automatically.
3. **PyInstaller** — `build.py` installs it if it is missing.

## Building

```
package.bat                    full build
```

or directly:

```
python packaging/build.py
```

Options:

| Flag | Effect |
| --- | --- |
| `--clean` | delete `build/` and `dist/` first |
| `--skip-browsers` | do not download the Playwright browser |
| `--skip-installer` | stop after `dist/ZaraAI` (no Inno Setup needed) |

The build takes a few minutes. The first run also downloads a Chromium build
(~150 MB) into `.playwright-browsers/` so browser automation works offline.

## How it fits together

**Step 1 — PyInstaller** (`zara.spec`) produces `dist/ZaraAI/`, a `--onedir`,
`--windowed` bundle. `--windowed` is what suppresses the black console window.

**Step 2 — Inno Setup** (`installer.iss`) wraps that folder into
`ZaraSetup.exe`, installing to `{autopf}\Zara AI` with shortcuts and an
uninstaller.

## Three things worth knowing

**The layout is flat, on purpose.** Zara finds every runtime file relative to
the executable (`get_base_dir()` returns `Path(sys.executable).parent` when
frozen). PyInstaller 6 otherwise puts collected files in an `_internal`
sub-folder, which would leave the app looking for `config/` and `assists/`
where they are not. The spec sets `contents_directory="."` to keep the exe and
its data side by side. Do not remove that line.

**`actions/` and `plugins/` ship as source.** Zara discovers its tools at
runtime by scanning those folders for `.py` files and loading each one, so they
are bundled as data rather than compiled in. Removing them from the spec's
`datas` would ship an app with no tools.

**Write permissions are scoped to data folders.** The installer grants
`users-modify` on `config\`, `memory\` and `uploads\` only — the folders the app
writes to at run time. Program files stay read-only, so an unprivileged user
cannot tamper with the executable. This is why the installer needs admin rights.

## Customising

Version and identity live in two places; keep them in step:

- `packaging/zara.spec` — `APP_NAME`, and `build/version_info.txt` content
- `packaging/installer.iss` — `MyAppName`, `MyAppVersion`, `MyAppPublisher`,
  `MyAppURL`

The `AppId` GUID in `installer.iss` identifies the product for upgrades and
uninstall. **Never change it** after a release, or a new version will install
alongside the old one instead of replacing it.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| App starts, no avatar / no prompt / no API key prompt | `contents_directory="."` missing from the spec, so data went into `_internal/` |
| `ModuleNotFoundError` at runtime | add the module to `hiddenimports` in `zara.spec` |
| App is very large (> 500 MB) | a heavy optional package slipped past `excludes`; check the PyInstaller log |
| Browser automation says "browser not found" | the browser was not bundled; rebuild without `--skip-browsers` |
| "Could not save API key" after install | the `[Dirs]` permissions did not apply; reinstall as admin |
| `ISCC.exe` not found | Inno Setup is not installed, or is in a non-default path — add it to PATH |
| Antivirus flags `ZaraAI.exe` | common for PyInstaller output; sign the exe, or report a false positive |

## Distribution

`dist/ZaraSetup.exe` is the file to publish. It is self-contained: the target PC
needs no Python and no separate downloads. The user runs it, and Zara appears in
the Start Menu.

For public releases, code-sign both `ZaraAI.exe` and `ZaraSetup.exe` to avoid
SmartScreen warnings. Add `SignTool` settings to `[Setup]` in `installer.iss`
once you have a certificate.
