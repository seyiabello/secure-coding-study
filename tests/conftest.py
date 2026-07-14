import sys
from pathlib import Path
# Add backend/ to path so tests can import multiagent, rag, mcp_servers, etc.
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
