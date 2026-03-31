import sys
import os
# jmem-mcp-server has the enhanced engine (L4/L5/L6); must be first on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'jmem-mcp-server'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))
