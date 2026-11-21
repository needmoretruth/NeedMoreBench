"""Entry point of the packaged app (PyInstaller on Windows and macOS): the same as `python -m nmb`."""
import sys

from nmb.config import use_real_folders
from nmb.ui.app import main

if __name__ == "__main__":
    use_real_folders()
    sys.exit(main(sys.argv))
