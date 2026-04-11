#!/usr/bin/env python3
"""
Inject Valid: enum documentation lines into tool docstrings that are missing them.

This processes the modular granular server files (src/granular/*.py) and adds
appropriate enum documentation to Args: sections.

Usage:
    python3 scripts/inject_enum_docs.py --dry-run   # preview
    python3 scripts/inject_enum_docs.py             # actually inject
"""

import ast
import re
import sys
from pathlib import Path

DRY_RUN = "--dry-run" in sys.argv
GRANULAR_DIR = Path("src/granular")


# ─── Enum definitions ────────────────────────────────────────────────────────

ENUM_VALUES = {
    "track_type": {
        "values": ['"video"', '"audio"', '"subtitle"'],
        "display": 'video", "audio", "subtitle',
        "pattern": r"(track_type.*?)(Valid:.*?\n)?",
    },
    "page": {
        "values": ['"edit"', '"cut"', '"color"', '"fusion"', '"fairlight"', '"deliver"'],
        "display": 'edit", "cut", "color", "fusion", "fairlight", "deliver',
        "pattern": r"(page.*?)(Valid:.*?\n)?",
    },
    "color": {
        "values": [
            "Blue",
            "Cyan",
            "Green",
            "Yellow",
            "Red",
            "Pink",
            "Purple",
            "Fuchsia",
            "Rose",
            "Lavender",
            "SkyBlue",
            "Mint",
            "Lemon",
            "Sand",
            "Cocoa",
            "Cream",
        ],
        "display": "Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream",
        "pattern": r"(color.*?)(Valid:.*?\n)?",
    },
    "keyframe_mode": {
        "values": ["0=Linear", "1=Bezier", "2=Constant"],
        "display": "0=Linear, 1=Bezier, 2=Constant",
        "pattern": r"(keyframe_mode.*?)(Valid:.*?\n)?",
    },
    "interpolation": {
        "values": ["Linear", "Bezier", "EaseIn", "EaseOut", "EaseInOut"],
        "display": "Linear, Bezier, EaseIn, EaseOut, EaseInOut",
        "pattern": r"(interpolation.*?)(Valid:.*?\n)?",
    },
    "retime_process": {
        "values": ['"nearest" (0)', '"frame_blend" (2)', '"optical_flow" (3)'],
        "display": '"nearest" (0), "frame_blend" (2), "optical_flow" (3)',
        "pattern": r"(process.*?)(Valid:.*?\n)?",
    },
    "motion_estimation": {
        "values": ["0", "1", "2", "3", "4", "5", "6"],
        "display": "0-6",
        "pattern": r"(motion_estimation.*?)(Valid:.*?\n)?",
    },
    "cache": {
        "values": ['"Auto"', '"On"', '"Off"'],
        "display": '"Auto", "On", "Off"',
        "pattern": r"(cache.*?)(Valid:.*?\n)?",
    },
    "version_type": {
        "values": ["0=local", "1=remote"],
        "display": "0=local, 1=remote",
        "pattern": r"(version_type.*?)(Valid:.*?\n)?",
    },
    "magic_mask_mode": {
        "values": ['"F" (forward)', '"B" (backward)', '"BI" (bidirectional)'],
        "display": '"F" (forward), "B" (backward), "BI" (bidirectional)',
        "pattern": r"(mode.*?)(Valid:.*?\n)?",
    },
    "stereo_eye": {
        "values": ['"left"', '"right"'],
        "display": '"left", "right"',
        "pattern": r"(stereo_eye.*?)(Valid:.*?\n)?",
    },
    "grade_mode": {
        "values": ["0", "1", "2"],
        "display": "0, 1, 2",
        "pattern": r"(grade_mode.*?)(Valid:.*?\n)?",
    },
    "format": {
        "values": ["dpx", "cin", "tif", "jpg", "png", "ppm", "bmp", "xpm", "drx"],
        "display": "dpx, cin, tif, jpg, png, ppm, bmp, xpm, drx",
        "pattern": r"(format.*?)(Valid:.*?\n)?",
    },
    "composite_mode": {
        "values": [
            "Normal",
            "Add",
            "Subtract",
            "Multiply",
            "Screen",
            "Overlay",
            "Darken",
            "Lighten",
            "ColorDodge",
            "ColorBurn",
            "LinearDodge",
            "LinearBurn",
            "HardLight",
            "SoftLight",
            "PinLight",
            "VividLight",
            "Difference",
            "Exclusion",
            "Hue",
        ],
        "display": "Normal, Add, Subtract, Multiply, Screen, Overlay, Darken, Lighten, ColorDodge, ColorBurn, LinearDodge, LinearBurn, HardLight, SoftLight, PinLight, VividLight, Difference, Exclusion, Hue",
        "pattern": r"(composite_mode.*?)(Valid:.*?\n)?",
    },
    "node_index": {
        "values": None,  # Just int
        "display": None,
        "pattern": r"(node_index.*?)(Valid:.*?\n)?",
    },
    "marker_note": {
        "values": None,
        "display": None,
        "pattern": None,
    },
}


def get_enum_for_param(param_name):
    """Determine which enum (if any) applies to a parameter."""
    pn = param_name.lower()

    if "track_type" in pn:
        return "track_type"
    if "page" in pn and ("media" in pn or "cut" in pn or "edit" in pn or "fusion" in pn or "color" in pn or "fairlight" in pn or "deliver" in pn):
        return "page"
    if "color" in pn and ("marker" in pn or "flag" in pn):
        return "color"
    if "marker" in pn and "color" in pn:
        return "color"
    if "keyframe_mode" in pn:
        return "keyframe_mode"
    if "interpolation" in pn:
        return "interpolation"
    if "process" in pn and "retime" in pn:
        return "retime_process"
    if "retime" in pn and "process" in pn:
        return "retime_process"
    if "motion_estimation" in pn:
        return "motion_estimation"
    if "cache" in pn and ("fusion" in pn or "color" in pn):
        return "cache"
    if "version_type" in pn:
        return "version_type"
    if "magic_mask" in pn or ("mask" in pn and "mode" in pn):
        return "magic_mask_mode"
    if "stereo" in pn and "eye" in pn:
        return "stereo_eye"
    if "grade" in pn and "mode" in pn:
        return "grade_mode"
    if "format" in pn and ("still" in pn or "export" in pn or "image" in pn):
        return "format"
    if "composite" in pn and "mode" in pn:
        return "composite_mode"
    if "node_index" in pn or "node" in pn and "index" in pn:
        return "node_index"

    return None


def parse_args_section(docstring):
    """Extract Args: section from docstring and return structured info.

    Returns list of param entries with: name, description, has_valid, line_index
    """
    if "Args:" not in docstring:
        return None

    # Find the Args: section
    args_start = docstring.find("Args:")

    # Find what comes after Args: — either Returns: or end of docstring
    returns_pos = docstring.find("Returns:", args_start)
    notes_pos = docstring.find("Note:", args_start)

    end_positions = []
    if returns_pos != -1:
        end_positions.append(returns_pos)
    if notes_pos != -1:
        end_positions.append(notes_pos)

    end_pos = min(end_positions) if end_positions else len(docstring)

    args_lines = docstring[args_start:end_pos].split("\n")

    # Skip "Args:" line (index 0), process from index 1
    params = []
    for i, line in enumerate(args_lines[1:], start=1):
        stripped = line.lstrip()

        # Skip empty lines and section headers (higher indent levels)
        if not stripped or stripped.startswith(("Returns:", "Note:", "Raises:", "Valid:")):
            continue

        # Check if this looks like a param: description line
        # It should have a colon after the param name with description after
        if ":" in stripped:
            colon_pos = stripped.index(":")
            param_name = stripped[:colon_pos].strip()
            description = stripped[colon_pos + 1 :].strip()

            # Check if next line is Valid:
            has_valid = False
            if i + 1 < len(args_lines):
                next_line_stripped = args_lines[i + 1].lstrip()
                if next_line_stripped.startswith("Valid:"):
                    has_valid = True

            params.append(
                {
                    "name": param_name,
                    "description": description,
                    "has_valid": has_valid,
                    "line_index": i,
                }
            )

    return params


def inject_enums_into_docstring(docstring, params_with_enums):
    """Add Valid: lines to Args: section for params that need them.

    Uses line-by-line processing to handle multi-line Args sections correctly.
    """
    if not params_with_enums:
        return docstring

    # Build a lookup: param_name -> enum_key
    param_to_enum = {p[0]: p[1] for p in params_with_enums}

    # Find Args: section bounds
    if "Args:" not in docstring:
        return docstring

    args_start = docstring.find("Args:")
    returns_pos = docstring.find("Returns:", args_start)
    notes_pos = docstring.find("Note:", args_start)
    end_positions = [p for p in [returns_pos, notes_pos] if p != -1]
    end_pos = min(end_positions) if end_positions else len(docstring)

    before_args = docstring[:args_start]
    args_section = docstring[args_start:end_pos]
    after_args = docstring[end_pos:]

    # Process Args: section line by line
    args_lines = args_section.split("\n")
    new_args_lines = []
    i = 0

    while i < len(args_lines):
        line = args_lines[i]
        stripped = line.lstrip()

        new_args_lines.append(line)

        # Check if this is a parameter line (has "param_name: description")
        if stripped and ":" in stripped and not stripped.startswith(("Args:", "Returns:", "Note:", "Raises:", "Valid:")):
            colon_pos = stripped.index(":")
            param_name = stripped[:colon_pos].strip()

            if param_name in param_to_enum:
                enum_key = param_to_enum[param_name]
                enum_info = ENUM_VALUES.get(enum_key)

                if enum_info and enum_info["display"]:
                    # Check if Valid: already exists
                    has_valid = i + 1 < len(args_lines) and args_lines[i + 1].lstrip().startswith("Valid:")

                    if not has_valid:
                        # Add Valid: line with proper indentation
                        # Valid: should be at same indent as description continuation
                        # (4 spaces more than the param line's base indent)
                        indent = len(line) - len(stripped)
                        valid_indent = " " * (indent + 4)
                        new_args_lines.append(f"{valid_indent}Valid: {enum_info['display']}")

        i += 1

    return before_args + "\n".join(new_args_lines) + after_args


def process_tool(src):
    """Process a single tool's source and inject enum docs if needed."""
    # Extract docstring
    docstring_match = re.search(r'"""(.*?)"""', src, re.DOTALL)
    if not docstring_match:
        return src, False

    docstring = docstring_match.group(1)

    # Parse Args: section
    args_info = parse_args_section(docstring)
    if not args_info:
        return src, False

    # Find params that need enums
    params_needed = []
    for param in args_info:
        if param["has_valid"]:
            continue
        enum_key = get_enum_for_param(param["name"])
        if enum_key:
            params_needed.append((param["name"], enum_key))

    if not params_needed:
        return src, False

    # Inject enums
    new_docstring = inject_enums_into_docstring(docstring, params_needed)

    if new_docstring == docstring:
        return src, False

    # Replace docstring in source
    new_src = src.replace('"""' + docstring + '"""', '"""' + new_docstring + '"""', 1)

    return new_src, True


def process_module_file(filepath):
    """Process a single module file."""
    content = filepath.read_text()

    # Find @mcp.tool() positions
    tool_starts = [(m.start(), m.group(0)) for m in re.finditer(r"@mcp\.tool\(\)", content)]

    if not tool_starts:
        return content, 0, 0

    # Extract each tool's content
    tools_data = []
    for i, (start, _) in enumerate(tool_starts):
        next_start = tool_starts[i + 1][0] if i + 1 < len(tool_starts) else len(content)
        tool_content = content[start:next_start]
        tools_data.append((start, next_start, tool_content))

    # Process each tool
    new_content = content
    modified_count = 0
    total_count = len(tools_data)

    # Process in reverse order to preserve positions
    for start, end, tool_src in reversed(tools_data):
        new_tool_src, was_modified = process_tool(tool_src)

        if was_modified:
            new_content = new_content[:start] + new_tool_src + new_content[end:]
            modified_count += 1

    return new_content, total_count, modified_count


def main():
    print("📝 Injecting enum documentation into granular server docstrings...\n")

    total_tools = 0
    total_modified = 0

    for module_file in sorted(GRANULAR_DIR.glob("*.py")):
        if module_file.name == "__init__.py":
            continue

        new_content, tool_count, modified = process_module_file(module_file)
        total_tools += tool_count
        total_modified += modified

        if modified > 0:
            print(f"  {'📝' if DRY_RUN else '✅'} {module_file.name}: {modified}/{tool_count} tools updated")
            if not DRY_RUN:
                module_file.write_text(new_content)
        else:
            print(f"  ⏭️  {module_file.name}: {tool_count} tools (no changes needed)")

    print(f"\n📊 Total: {total_modified}/{total_tools} tools updated")

    if DRY_RUN:
        print("\n⚠️  Dry run — no files were modified")
        print("   Run without --dry-run to apply changes")
    else:
        print("\n✅ Changes applied")
        # Verify syntax
        print("\n🔍 Verifying syntax...")
        for module_file in sorted(GRANULAR_DIR.glob("*.py")):
            try:
                ast.parse(module_file.read_text())
            except SyntaxError as e:
                print(f"  ❌ {module_file.name}: syntax error at line {e.lineno}")
                return

        # Verify tool counts
        total_decorators = 0
        for module_file in sorted(GRANULAR_DIR.glob("*.py")):
            if module_file.name == "__init__.py":
                continue
            count = module_file.read_text().count("@mcp.tool()")
            total_decorators += count

        print(f"✅ All files valid — {total_decorators} @mcp.tool() decorators verified")


if __name__ == "__main__":
    main()
