#!/usr/bin/env python3
"""
DaVinci Resolve MCP Server (Granular)
Version: 2.2.0 — 356 tools across 10 categories
"""

import os
import sys

# ── Resolve API path setup ────────────────────────────────────────
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from src.utils.platform import setup_environment, get_platform, get_resolve_paths
paths = get_resolve_paths()
RESOLVE_API_PATH = paths['api_path']
RESOLVE_LIB_PATH = paths['lib_path']
RESOLVE_MODULES_PATH = paths['modules_path']
os.environ['RESOLVE_SCRIPT_API'] = RESOLVE_API_PATH
os.environ['RESOLVE_SCRIPT_LIB'] = RESOLVE_LIB_PATH
if RESOLVE_MODULES_PATH not in sys.path:
    sys.path.append(RESOLVE_MODULES_PATH)

# ── Import utility functions ────────────────────────────────────
from src.utils.object_inspection import (
    inspect_object, get_object_methods, get_object_properties,
    print_object_help, convert_lua_to_python,
)
from src.utils.layout_presets import (
    list_layout_presets, save_layout_preset, load_layout_preset,
    export_layout_preset, import_layout_preset, delete_layout_preset,
)
from src.utils.app_control import (
    quit_resolve_app, launch_resolve_app, get_resolve_version,
)
from src.utils.project_manager_tools import (
    list_projects, get_current_project_name, get_project_settings,
)
from src.utils.timeline_tools import (
    get_current_timeline, get_timeline_tracks,
)
from src.utils.media_pool_tools import (
    list_media_pool_clips, import_media,
)

# ── Import granular package (registers all @mcp.tool decorators) ──
from granular import mcp

if __name__ == '__main__':
    mcp.run()