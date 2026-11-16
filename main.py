"""Entry point (the file PyInstaller freezes).

Dev flags: --demo (invented library), --screenshots DIR and --selftest (both offscreen, no window).
"""
import sys

from camera_business_use.ui.app import main

if __name__ == "__main__":
    sys.exit(main())
