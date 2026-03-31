"""Standalone launcher for textual-serve subprocess.

This file is invoked by textual-serve as a shell subprocess.
It must work regardless of the current working directory.
"""

import sys
from pathlib import Path

# Absolute path to project root
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Change to project dir so config.json, logs/, reports/ resolve correctly
import os
os.chdir(PROJECT_ROOT)

from ui.app import AmazonPPCApp

app = AmazonPPCApp()
app.run()
