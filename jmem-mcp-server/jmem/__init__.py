"""JMEM MCP Server — thin wrapper re-exporting from python/jmem."""
import sys, os
# Add the python/ directory to path so we import the authoritative jmem
_py_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "python")
if _py_dir not in sys.path:
    sys.path.insert(0, _py_dir)

from jmem.engine import JMemEngine, MemoryLevel, MemoryNote  # noqa: F401

__version__ = "1.0.0"
