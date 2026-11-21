"""python3 -m nmb opens the app."""
import sys

from .config import use_real_folders
from .ui.app import main

use_real_folders()  # only the app itself uses the user's settings and records
sys.exit(main())
