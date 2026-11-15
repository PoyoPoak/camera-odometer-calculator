---
name: validate
description: Test and validate changes to Camera Odometer Calculator. Use before reporting a change as done or committing it, to pick and run only the checks that fit what changed (engine, UI, or build).
---

# Validate

Run the checks for what changed. Do not run everything by reflex: the build takes a minute and the exe run needs a Windows folder.

| What changed | Run |
| --- | --- |
| Engine: `calc.py`, `store.py`, `exif.py`, `scan.py`, `models.py`, `tests/` | 1 |
| UI: `camera_odometer/ui/`, `main.py` | 2, then 3 for anything visible |
| `models.py` or an engine function the UI calls | 1 and 2 |
| Build: `scripts/`, `requirements.txt`, `assets/`, or how `exif.py` finds ExifTool | 4 |
| Docs only | nothing |

Setup, if `.venv-win/` or `vendor/` is missing: see `docs/development.md`.

**No check may open a window on the desktop.** `--selftest` and `--screenshots` run offscreen and exit by themselves. Never start the app or the exe without one of them.

## 1. Engine unit tests

```bash
python3 -m unittest discover -s tests
```

Runs in WSL. Needs neither Qt nor ExifTool.

## 2. UI selftest

```bash
.venv-win/Scripts/python.exe main.py --selftest
```

Pass: prints `selftest: N checks passed` and exits 0. Any exception in a slot or event handler fails the run.

## 3. UI screenshots

```bash
.venv-win/Scripts/python.exe main.py --screenshots build/screens
```

- Writes one PNG per screen from the demo library; names ending in `-min` are at the minimum window size.
- **Open the PNGs of the screens you changed with the Read tool** and compare them with `docs/design.md`. Exit code 0 only means nothing crashed.

## 4. Build and exe smoke run

The exe has to run from a Windows drive. Use the Windows folder the user has approved for build output; ask if you do not know it, and write nowhere else on the Windows side.

```bash
.venv-win/Scripts/python.exe scripts/build.py --deploy '<approved Windows folder>'
'<same folder as a /mnt/... path>/CameraOdometer.exe' --selftest; echo "exit $?"
```

- Pass: `selftest: N checks passed` and `exit 0`. The first run of a new exe takes 10 to 20 s.
- `Invalid argument` or `WinError 4551` means Smart App Control blocked the file: see Troubleshooting in `docs/development.md`. It is not a bug in the build.
- **Limit**: the selftest uses demo data and never starts ExifTool, so it does not prove the bundled ExifTool works. After a change to the ExifTool bundling, ask the user to open the exe and check the shutter count of one real raw file.
- Startup time only matters when the bundle contents change. The numbers to compare with are in `docs/development.md`.
