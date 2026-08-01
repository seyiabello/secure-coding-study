import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# Tests mock all OpenAI calls, so a placeholder key is enough to satisfy config.py.
os.environ.setdefault("OPENAI_API_KEY", "sk-test-placeholder")
