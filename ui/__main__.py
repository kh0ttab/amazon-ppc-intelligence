"""Entry point for textual-serve: python -m ui.app"""

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.app import AmazonPPCApp

app = AmazonPPCApp()
app.run()
