# tests/conftest.py
import sys
from pathlib import Path

# Ensure src/ is on sys.path so tests can import the package during test collection
ROOT = Path(__file__).resolve().parents[1]
SRC = str(ROOT / "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
