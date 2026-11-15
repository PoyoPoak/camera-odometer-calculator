"""Download the pinned ExifTool into vendor/ (git-ignored). Standard library only.

    python scripts/fetch_exiftool.py

    vendor/exiftool-win/   exiftool.exe + exiftool_files/   bundled into the Windows exe
    vendor/exiftool-perl/  Perl distribution                 Linux dev: perl vendor/exiftool-perl/exiftool

Does nothing for a package that is already there at VERSION. To bump: change
VERSION and both hashes (published on https://exiftool.org) and run it again.
"""
import hashlib
import shutil
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "13.63"
URL = "https://sourceforge.net/projects/exiftool/files/{}/download"
VENDOR = Path(__file__).resolve().parent.parent / "vendor"

# name: (archive, sha256, file that carries the version string)
PACKAGES = {
    "win": (f"exiftool-{VERSION}_64.zip",
            "7a4bff4b1d6ee15adef882837847f76c0ed23228d294feed285939b6c9b293bd",
            "exiftool_files/exiftool.pl"),
    "perl": (f"Image-ExifTool-{VERSION}.tar.gz",
             "c6438851b971886f2eb35426ea5bc8960f34ae4eddeca3198a57af5b0ad49cbd",
             "exiftool"),
}


def ensure(name: str, vendor: Path = VENDOR) -> Path:
    """Return vendor/exiftool-<name>, downloading and unpacking it if needed."""
    archive, sha256, marker = PACKAGES[name]
    target = vendor / f"exiftool-{name}"
    marker = target / marker
    if marker.is_file() and f"'{VERSION}'" in marker.read_text(errors="replace")[:2000]:
        return target

    print(f"fetching {archive} ...", flush=True)
    with urllib.request.urlopen(URL.format(archive), timeout=120) as response:
        data = response.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sha256:
        sys.exit(f"{archive}: SHA-256 mismatch\n  expected {sha256}\n  got      {digest}")

    vendor.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=vendor) as tmp:
        packed = Path(tmp) / archive
        packed.write_bytes(data)
        if archive.endswith(".zip"):
            with zipfile.ZipFile(packed) as z:
                z.extractall(tmp)
        else:
            with tarfile.open(packed) as t:
                t.extractall(tmp, filter="data")
        packed.unlink()
        (top,) = Path(tmp).iterdir()  # both archives hold exactly one top-level folder
        if name == "win":
            (top / "exiftool(-k).exe").rename(top / "exiftool.exe")  # "(-k)" means "pause before exit"
        shutil.rmtree(target, ignore_errors=True)
        top.rename(target)
    print(f"unpacked {target}")
    return target


if __name__ == "__main__":
    for package in PACKAGES:
        ensure(package)
