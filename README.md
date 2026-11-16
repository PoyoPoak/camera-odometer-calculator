# Camera Odometer Calculator

Windows desktop app that works out what share of a camera's use was for business, from shutter counts.

![Results screen](docs/images/results.png)

- Point it at your photo folders (one or several) and pick a tax year.
- It finds each camera body's first and last shot of the year (the yearly odometer).
- You flip through folders and mark each **Personal** (`←`) or **Business** (`→`).
- It reports the business-use percentage and exports the breakdown as CSV.
- It can also show the shutter count of any single image.

## Download and run

- `CameraOdometer.exe` is produced by `scripts/build.py` (below) and lands in `dist/`. One file, Windows 10 / 11, 64-bit.
- Put it in a folder of its own that you can write to and start it. It keeps its data in a hidden `.data` folder next to itself and only reads your photos.
- The first start takes 10 to 20 seconds while Windows scans the new file.
- The exe is **not code-signed**: Smart App Control or SmartScreen may block it.
- How to use it: [user guide](docs/user-guide.md).

## Build from source

Needs Windows Python 3.12. From WSL (or any shell, with the paths adapted):

```bash
python.exe -m venv .venv-win
chmod +x .venv-win/Scripts/*.exe        # WSL only
.venv-win/Scripts/python.exe -m pip install -r requirements.txt
.venv-win/Scripts/python.exe scripts/build.py
```

The result is `dist/CameraOdometer.exe`. Details, tests and troubleshooting: [development guide](docs/development.md).

## Documentation

See the [wiki](docs/README.md).

## Credits

- Metadata is read with [ExifTool](https://exiftool.org) by Phil Harvey, bundled unmodified. ExifTool is free software under the same terms as Perl itself (the Perl Artistic License or the GPL); its Windows package carries its own licence files.
- The interface is built with [Qt for Python](https://doc.qt.io/qtforpython-6/) (PySide6, LGPL).
