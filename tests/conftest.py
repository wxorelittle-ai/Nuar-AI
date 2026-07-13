"""Делает корень пакета restopulse/ импортируемым в тестах без установки."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
