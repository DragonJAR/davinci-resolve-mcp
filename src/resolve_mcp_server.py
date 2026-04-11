#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server (Granular)
Version: 2.2.0 — 356 tools across 10 categories
"""

import os
import sys

# ── Resolve API path setup ────────────────────────────────────────
current_dir = os.path.dirname(os.path.abspath(__file__))
# Add project root so "from src.utils.platform import ..." works
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from src.utils.platform import get_resolve_paths

paths = get_resolve_paths()
RESOLVE_API_PATH = paths["api_path"]
RESOLVE_LIB_PATH = paths["lib_path"]
RESOLVE_MODULES_PATH = paths["modules_path"]
os.environ["RESOLVE_SCRIPT_API"] = RESOLVE_API_PATH
os.environ["RESOLVE_SCRIPT_LIB"] = RESOLVE_LIB_PATH
if RESOLVE_MODULES_PATH not in sys.path:
    sys.path.append(RESOLVE_MODULES_PATH)

# ── Import utility functions ────────────────────────────────────

# ── Import granular package (registers all @mcp.tool decorators) ──
from granular import mcp

if __name__ == "__main__":
    mcp.run()
