#!/usr/bin/env python3
"""
Split resolve_mcp_server.py into modular files by API class.
Run once to split, can be run again to re-split from the original backup.

Usage:
    python3 scripts/split_granular.py --dry-run   # preview
    python3 scripts/split_granular.py             # actually split
    python3 scripts/split_granular.py --restore  # restore from backup
"""

import ast
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
RESTORE = "--restore" in sys.argv
SRC_DIR = Path("src")
GRANULAR_DIR = SRC_DIR / "granular"
SOURCE_FILE = SRC_DIR / "resolve_mcp_server.py"
BACKUP_FILE = SRC_DIR / "resolve_mcp_server.py.backup_modsplit"


def load_source():
    if not SOURCE_FILE.exists():
        print(f"❌ {SOURCE_FILE} not found.")
        sys.exit(1)
    return SOURCE_FILE.read_text()


def extract_all_tools(content):
    """Use AST to extract all @mcp.tool decorated functions.

    NOTE: AST node.lineno is the line of the 'def', NOT the decorator.
    We must include the decorator line(s) before the def.
    """
    tree = ast.parse(content)
    lines = content.split("\n")

    tools = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                dec_src = ast.unparse(dec) if hasattr(ast, "unparse") else ""
                if "mcp.tool" in dec_src:
                    # Decorator line(s) are BEFORE the def lineno
                    # Include from decorator to end of function body
                    dec_lineno = getattr(dec, "lineno", node.lineno)
                    start = dec_lineno - 1  # 0-indexed
                    end = node.end_lineno
                    src = "\n".join(lines[start:end])
                    tools.append(
                        {
                            "name": node.name,
                            "lineno": start + 1,  # 1-indexed for reference
                            "end_lineno": end,
                            "src": src,
                        }
                    )
                    break
    return tools


def categorize_tool(func_name, src):
    """Determine primary API class based on most-used API variable."""
    first_def_end = src.find("):")
    body = src[first_def_end + 2 :] if first_def_end != -1 else src

    api_calls = {
        "resolve": len(re.findall(r"\bresolve\b\.", body)),
        "project": len(re.findall(r"\bproject\b\.", body)),
        "pm": len(re.findall(r"\bpm\b\.", body)),
        "tl": len(re.findall(r"\btl\b\.", body)),
        "item": len(re.findall(r"\bitem\b\.", body)),
        "clip": len(re.findall(r"\bclip\b\.", body)),
        "folder": len(re.findall(r"\bfolder\b\.", body)),
        "ms": len(re.findall(r"\bms\b\.", body)),
        "mp": len(re.findall(r"\bmp\b\.", body)),
        "gallery": len(re.findall(r"\bgallery\b\.", body)),
        "graph": len(re.findall(r"\bgraph\b\.", body)),
        "cg": len(re.findall(r"\bcg\b\.", body)),
        "fusion": len(re.findall(r"\bfusion\b\.", body)),
    }

    mapping = {
        "resolve": "resolve_control",
        "pm": "project_manager",
        "project": "project",
        "tl": "timeline",
        "item": "timeline_item",
        "clip": "media_pool_item",
        "folder": "folder",
        "ms": "media_storage",
        "mp": "media_pool",
        "gallery": "gallery",
        "graph": "graph",
        "cg": "color_group",
        "fusion": "fusion_comp",
    }

    sorted_ops = sorted(api_calls.items(), key=lambda x: x[1], reverse=True)
    if sorted_ops[0][1] > 0:
        return mapping.get(sorted_ops[0][0], "resolve_control")

    # Name-based fallback
    if any(k in func_name for k in ["resolve", "page", "quit"]):
        return "resolve_control"
    if any(
        k in func_name
        for k in ["project", "open_project", "create_project", "save_project", "close_project", "list_projects"]
    ):
        return "project"
    if any(k in func_name for k in ["timeline", "track", "marker"]):
        return "timeline"
    if any(k in func_name for k in ["media_pool", "bin", "import_media", "delete_media", "move_media"]):
        return "media_pool"
    if any(k in func_name for k in ["clip", "item", "media_pool_item"]):
        return "media_pool_item"
    if any(k in func_name for k in ["folder"]):
        return "folder"
    if any(k in func_name for k in ["gallery", "still", "album"]):
        return "gallery"
    if any(k in func_name for k in ["graph", "node", "lut"]):
        return "graph"
    if any(k in func_name for k in ["color_group", "colorgroup"]):
        return "color_group"
    if any(k in func_name for k in ["fusion", "comp"]):
        return "fusion_comp"
    if any(k in func_name for k in ["storage", "volume"]):
        return "media_storage"
    if any(k in func_name for k in ["project_manager", "projectmanager"]):
        return "project_manager"

    return "resolve_control"


def find_all_helpers(content, tool_names):
    """Extract all non-tool module-level functions."""
    tree = ast.parse(content)
    lines = content.split("\n")
    helpers = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name not in tool_names:
                src = "\n".join(lines[node.lineno - 1 : node.end_lineno])
                helpers[node.name] = src

    return helpers


def dedent_source(src):
    """Remove leading indentation to make code module-level.

    Detects the minimum indentation of non-empty lines and removes it.
    """
    lines = src.split("\n")
    # Find minimum indent of non-empty lines
    min_indent = float("inf")
    for line in lines:
        stripped = line.lstrip()
        if stripped:  # non-empty line
            indent = len(line) - len(stripped)
            min_indent = min(min_indent, indent)

    if min_indent == float("inf") or min_indent == 0:
        return src

    # Remove min_indent from each line
    result = []
    for line in lines:
        if line.lstrip():
            result.append(line[min_indent:])
        else:
            result.append("")

    return "\n".join(result)


def fix_docstring_indent(content):
    """Ensure Args: and Valid: lines have proper indentation within docstrings."""
    lines = content.split("\n")
    result = []
    in_docstring = False
    docstring_indent = None

    for line in lines:
        stripped = line.lstrip()
        indent = len(line) - len(stripped)

        if '"""' in line or "'''" in line:
            if not in_docstring:
                in_docstring = True
                docstring_indent = indent
            else:
                in_docstring = False
                docstring_indent = None
            result.append(line)
        elif in_docstring and stripped.startswith(("Args:", "Valid:", "Returns:", "Note:", "Raises:")):
            expected = docstring_indent + 4
            if indent != expected:
                result.append(" " * expected + stripped)
            else:
                result.append(line)
        else:
            result.append(line)

    return "\n".join(result)


def write_module(category, tools, all_helpers, dry_run=False):
    """Write a single module file."""
    lines = []
    lines.append("#!/usr/bin/env python3")
    lines.append(f'"""Granular server — {category} tools."""')
    lines.append("")
    lines.append("# ── Imports ──────────────────────────────────────────────────────")
    lines.append("import logging")
    lines.append("import os")
    lines.append("import sys")
    lines.append("import platform")
    lines.append("import subprocess")
    lines.append("import tempfile")
    lines.append("import time")
    lines.append("from typing import Dict, Any, List, Optional")
    lines.append("")
    lines.append("# ── Shared mcp server (defined in granular/__init__.py) ───────────")
    lines.append("from granular import mcp")
    lines.append("")
    lines.append("# ── Logger ──────────────────────────────────────────────────────")
    lines.append("logger = logging.getLogger(__name__)")
    lines.append("")

    # Add dedented helpers
    if all_helpers:
        lines.append("# ── Helpers ──────────────────────────────────────────────────────")
        for hname in sorted(all_helpers.keys()):
            dedented = dedent_source(all_helpers[hname])
            lines.append(dedented)
        lines.append("")

    # Add tools (sorted alphabetically) — they keep their original indentation
    lines.append("# ── Tools ────────────────────────────────────────────────────────")
    for t in sorted(tools, key=lambda x: x["name"]):
        fixed = fix_docstring_indent(t["src"])
        lines.append(fixed)
        lines.append("")  # Extra newline between tools

    content = "\n".join(lines)

    # Verify syntax
    try:
        ast.parse(content)
    except SyntaxError as e:
        print(f"  ⚠️  Syntax error in {category}: {e}")
        if not dry_run:
            raise

    module_file = GRANULAR_DIR / f"{category}.py"
    if dry_run:
        print(f"  [dry-run] {module_file.name}: {len(tools)} tools, {len(content):,} chars")
    else:
        module_file.write_text(content)
        print(f"  ✅ {module_file.name}: {len(tools)} tools, {len(content):,} chars")

    return content


def write_init(dry_run=False):
    """Write granular/__init__.py with mcp server + all tools."""
    cats = sorted([p.stem for p in GRANULAR_DIR.glob("*.py") if p.stem != "__init__" and p.stem != "resolve_control"])

    lines = [
        "#!/usr/bin/env python3",
        '"""Granular DaVinci Resolve MCP Server — modular package."""',
        "",
        "import logging",
        "from typing import Dict, Any",
        "",
        "# ── Create MCP server (MUST be defined before modules import it) ────",
        "from mcp.server.fastmcp import FastMCP",
        "mcp = FastMCP('davinci-resolve-granular')",
        "",
        "# ── Import all tool modules (they use the mcp instance above) ───────",
    ]

    for cat in cats:
        lines.append(f"from granular.{cat} import *")

    lines.extend(
        [
            "",
            "logger = logging.getLogger(__name__)",
            "",
        ]
    )

    content = "\n".join(lines)

    if dry_run:
        print(f"  [dry-run] __init__.py: {len(content)} chars")
    else:
        (GRANULAR_DIR / "__init__.py").write_text(content)
        print(f"  ✅ __init__.py: {len(content)} chars")

    return content


def write_entry_point(tools, dry_run=False):
    """Write thin entry point resolve_mcp_server.py."""
    cats = sorted([p.stem for p in GRANULAR_DIR.glob("*.py") if p.stem not in ("__init__", "resolve_control")])

    lines = [
        "#!/usr/bin/env python3",
        '"""',
        "DaVinci Resolve MCP Server (Granular)",
        f"Version: 2.2.0 — {len(tools)} tools across {len(cats) + 1} categories",
        '"""',
        "",
        "import os",
        "import sys",
        "",
        "# ── Resolve API path setup ────────────────────────────────────────",
        "current_dir = os.path.dirname(os.path.abspath(__file__))",
        "src_dir = os.path.join(current_dir, 'src')",
        "if src_dir not in sys.path:",
        "    sys.path.insert(0, src_dir)",
        "",
        "from src.utils.platform import setup_environment, get_platform, get_resolve_paths",
        "paths = get_resolve_paths()",
        "RESOLVE_API_PATH = paths['api_path']",
        "RESOLVE_LIB_PATH = paths['lib_path']",
        "RESOLVE_MODULES_PATH = paths['modules_path']",
        "os.environ['RESOLVE_SCRIPT_API'] = RESOLVE_API_PATH",
        "os.environ['RESOLVE_SCRIPT_LIB'] = RESOLVE_LIB_PATH",
        "if RESOLVE_MODULES_PATH not in sys.path:",
        "    sys.path.append(RESOLVE_MODULES_PATH)",
        "",
        "# ── Import utility functions ────────────────────────────────────",
        "from src.utils.object_inspection import (",
        "    inspect_object, get_object_methods, get_object_properties,",
        "    print_object_help, convert_lua_to_python,",
        ")",
        "from src.utils.layout_presets import (",
        "    list_layout_presets, save_layout_preset, load_layout_preset,",
        "    export_layout_preset, import_layout_preset, delete_layout_preset,",
        ")",
        "from src.utils.app_control import (",
        "    quit_resolve_app, launch_resolve_app, get_resolve_version,",
        ")",
        "from src.utils.project_manager_tools import (",
        "    list_projects, get_current_project_name, get_project_settings,",
        ")",
        "from src.utils.timeline_tools import (",
        "    get_current_timeline, get_timeline_tracks,",
        ")",
        "from src.utils.media_pool_tools import (",
        "    list_media_pool_clips, import_media,",
        ")",
        "",
        "# ── Import granular package (registers all @mcp.tool decorators) ──",
        "from granular import mcp",
        "",
        "if __name__ == '__main__':",
        "    mcp.run()",
    ]

    content = "\n".join(lines)

    if dry_run:
        print(f"  [dry-run] resolve_mcp_server.py entry point: {len(content)} chars")
    else:
        SOURCE_FILE.write_text(content)
        print(f"  ✅ resolve_mcp_server.py: thin entry point ({len(content)} chars)")

    try:
        ast.parse(content)
        print("  ✅ Entry point syntax OK")
    except SyntaxError as e:
        print(f"  ❌ Entry point syntax error: {e}")
        if not dry_run:
            raise


def main():
    if RESTORE:
        if BACKUP_FILE.exists():
            shutil.copy2(BACKUP_FILE, SOURCE_FILE)
            print(f"✅ Restored from {BACKUP_FILE}")
        else:
            print(f"❌ No backup found at {BACKUP_FILE}")
        return

    print(f"📖 Reading {SOURCE_FILE}...")
    content = load_source()

    if not DRY_RUN:
        shutil.copy2(SOURCE_FILE, BACKUP_FILE)
        print(f"💾 Backup: {BACKUP_FILE}")

    print("🔍 Parsing AST...")
    tools = extract_all_tools(content)
    print(f"   {len(tools)} tools extracted")

    # Categorize
    by_category = defaultdict(list)
    for t in tools:
        cat = categorize_tool(t["name"], t["src"])
        t["category"] = cat
        by_category[cat].append(t)

    print("\n📊 Distribution by category:")
    for cat, cat_tools in sorted(by_category.items(), key=lambda x: -len(x[1])):
        print(f"   {cat}: {len(cat_tools)}")

    # Extract helpers
    tool_names = {t["name"] for t in tools}
    print("\n🔧 Extracting helpers...")
    all_helpers = find_all_helpers(content, tool_names)
    print(f"   {len(all_helpers)} helpers found")

    # Create granular dir
    if not DRY_RUN:
        GRANULAR_DIR.mkdir(exist_ok=True)
        print(f"\n📁 {GRANULAR_DIR}/")

    # Write modules (resolve_control LAST so mcp is defined first)
    print("\n📦 Writing modules...")
    cats_ordered = sorted(by_category.keys(), key=lambda c: 0 if c == "resolve_control" else 1)

    for cat in cats_ordered:
        cat_tools = by_category[cat]
        if not cat_tools:
            continue
        try:
            write_module(cat, cat_tools, all_helpers, dry_run=DRY_RUN)
        except SyntaxError:
            if not DRY_RUN:
                print("  ❌ Failed, restoring backup...")
                shutil.copy2(BACKUP_FILE, SOURCE_FILE)
            raise

    # Write __init__.py (must come AFTER all modules since it imports them)
    write_init(dry_run=DRY_RUN)

    # Write entry point
    print()
    write_entry_point(tools, dry_run=DRY_RUN)

    # Final verification
    if not DRY_RUN:
        print("\n🔍 Verifying...")
        total_tools = 0
        for cat_file in sorted(GRANULAR_DIR.glob("*.py")):
            if cat_file.name == "__init__.py":
                continue
            src = cat_file.read_text()
            count = src.count("@mcp.tool()")
            total_tools += count
            print(f"   {cat_file.name}: {count} @mcp.tool()")

        print(f"   Total: {total_tools} tools")

        if total_tools != len(tools):
            print(f"   ⚠️  Mismatch: expected {len(tools)}, got {total_tools}")
            # Try to fix: restore backup
            shutil.copy2(BACKUP_FILE, SOURCE_FILE)
            print("   🔄 Restored backup")
            sys.exit(1)

        print("\n🎉 Modularization complete!")
        print(f"   {len(list(GRANULAR_DIR.glob('*.py'))) - 1} modules")
        print(f"   {total_tools} tools")
        print(f"   Backup: {BACKUP_FILE}")


if __name__ == "__main__":
    main()
