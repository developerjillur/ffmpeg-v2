"""Configurable artifact roots for the published historical experiment recipes."""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ffv2.config import WORK

LAB_ROOT = Path(os.environ.get('FFV2_LAB_ROOT', str(WORK / 'Work'))).expanduser().resolve()


def lab_path(relative=''):
    return LAB_ROOT / relative


def project_path(relative=''):
    return ROOT / relative
