"""Puts the skill directory and the tools directory on sys.path for the tests."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "drawing-diagrams"
TOOLS = ROOT / "tools"
for path in (str(TOOLS), str(SKILL)):
    if path not in sys.path:
        sys.path.insert(0, path)
