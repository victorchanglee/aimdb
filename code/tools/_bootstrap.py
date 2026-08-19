"""Put `code/` on sys.path so these scripts can import the mining_agent package.

The tools live one directory below the package they use. Running
`.venv/bin/python tools/<tool>.py` from `code/` puts `code/tools/` on
sys.path, not `code/`, so `import mining_agent` would fail. Importing this
module first fixes that, wherever the script is invoked from.
"""
import sys
from pathlib import Path

_CODE_DIR = str(Path(__file__).resolve().parent.parent)
if _CODE_DIR not in sys.path:
    sys.path.insert(0, _CODE_DIR)
