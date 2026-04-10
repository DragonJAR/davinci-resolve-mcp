#!/usr/bin/env python3
"""
Append enum documentation to granular server docstrings.

Strategy: Use AST to find @mcp.tool() decorated functions, then modify docstrings.
Creates backup, verifies syntax, restores on error.
"""

import ast
import re
import shutil
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "resolve_mcp_server.py"
BACKUP = SRC.with_suffix(".py.safebak")

# Map: (param_name_substring, func_name_substring) → text to append after param line
APPEND_RULES = [
    # Track type
    ("track_type", None, '\n        Valid: "video", "audio", "subtitle"'),
    # Page
    ("page", "switch_page", '\n        Valid: "edit", "cut", "color", "fusion", "fairlight", "deliver"'),
    # Marker color
    (
        "color",
        "marker",
        "\n        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream",
    ),
    # Cache
    ("cache_value", None, '\n        Valid: "Auto", "On", "Off"'),
    # Keyframe mode
    ("keyframe_mode", None, "\n        Valid: 0=Linear, 1=Bezier, 2=Constant"),
    # Grade mode
    ("grade_mode", None, "\n        Valid: 0=No keyframes, 1=Source Timecode aligned, 2=Start Frames aligned"),
    # Retime process
    ("process", "retime", '\n        Valid: "nearest" (0), "frame_blend" (2), "optical_flow" (3)'),
    # Motion estimation
    ("motion_estimation", None, "\n        Valid: 0-6 (0=project default, 6=speed_warp_faster)"),
    # Interpolation
    ("interpolation", "keyframe", "\n        Valid: Linear, Bezier, EaseIn, EaseOut, EaseInOut"),
    # Version type
    ("type", "version", "\n        Valid: 0=local, 1=remote"),
    # Magic mask mode
    ("mode", "magic_mask", '\n        Valid: "F" forward, "B" backward, "BI" bidirectional'),
    # CompositeMode
    (
        "CompositeMode",
        None,
        "\n        Valid: Normal, Add, Subtract, Multiply, Screen, Overlay, Darken, Lighten, ColorDodge, ColorBurn, LinearDodge, LinearBurn, HardLight, SoftLight, PinLight, VividLight, Difference, Exclusion, Hue",
    ),
    # Fusion tool_type
    (
        "tool_type",
        "fusion",
        "\n        Common: Merge, Background, TextPlus, Transform, Blur, ColorCorrector, RectangleMask, EllipseMask, Tracker, MediaIn, MediaOut, Loader, Saver, Glow, FilmGrain, CornerPositioner, DeltaKeyer, UltraKeyer",
    ),
    # Still format
    ("format", "still", '\n        Valid: "dpx", "cin", "tif", "jpg", "png", "ppm", "bmp", "xpm", "drx"'),
]


def get_decorated_funcs(content: str):
    """Find all @mcp.tool() decorated functions with their docstrings."""
    tree = ast.parse(content)
    result = []

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            # Check if function has @mcp.tool() decorator
            has_decorator = False
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call):
                    if isinstance(decorator.func, ast.Attribute):
                        if decorator.func.attr == "tool" and isinstance(decorator.func.value, ast.Name):
                            if decorator.func.value.id == "mcp":
                                has_decorator = True

            if has_decorator and node.body:
                # Get docstring
                docstring = ast.get_docstring(node)
                if docstring:
                    result.append(
                        {
                            "name": node.name,
                            "lineno": node.lineno,
                            "docstring": docstring,
                        }
                    )

    return result


def process_file(content: str) -> tuple[str, int]:
    """Process file content using AST and return modified content."""
    updates = 0
    lines = content.split("\n")

    # Find all @mcp.tool() decorated functions
    decorated_funcs = get_decorated_funcs(content)

    if not decorated_funcs:
        return content, 0

    # Sort by line number in descending order so we process from bottom to top
    # This prevents line index changes from affecting subsequent processing
    decorated_funcs.sort(key=lambda x: x["lineno"], reverse=True)

    # Process each function's docstring
    for func_info in decorated_funcs:
        func_name = func_info["name"]
        func_lineno = func_info["lineno"]
        docstring = func_info["docstring"]

        # Apply rules to this docstring
        modified_docstring = docstring
        for param_key, func_filter, append_text in APPEND_RULES:
            # Filter by function name
            if func_filter and func_filter not in func_name:
                continue

            # Check if param in docstring
            if param_key not in docstring:
                continue

            # Check if already documented
            if append_text in docstring:
                continue

            # Find param line and append text
            # Look for param name at start of line (after indentation)
            arg_pattern = rf"^(\s+{re.escape(param_key)}\s*:.*?)[^\n]*"
            docstring_lines = modified_docstring.split("\n")

            modified = False
            for j, ds_line in enumerate(docstring_lines):
                if not modified and re.match(arg_pattern, ds_line):
                    docstring_lines[j] = ds_line + append_text
                    modified = True
                    updates += 1
                    print(f"  → Modified {func_name}.{param_key}")

            if modified:
                modified_docstring = "\n".join(docstring_lines)
                break

        # If docstring was modified, update it in the content
        if modified_docstring != docstring:
            # Find the line number of the function (1-indexed in AST, 0-indexed in file)
            func_line_idx = func_lineno - 1

            # Find the docstring start in the lines
            docstring_start_idx = None
            for i in range(func_line_idx, len(lines)):
                # Must find """ at start of line (after whitespace) to be a docstring opening
                if '"""' in lines[i] and lines[i].lstrip().startswith('"""'):
                    docstring_start_idx = i
                    break

            if docstring_start_idx:
                # Find the docstring end by looking for the closing """
                # The closing """ must be at the same or lower indentation level
                # and not be part of the content (e.g., """ on its own line)
                start_indent = len(lines[docstring_start_idx]) - len(lines[docstring_start_idx].lstrip())
                docstring_end_idx = None
                for i in range(docstring_start_idx + 1, len(lines)):
                    # Check if this line contains """
                    if '"""' in lines[i]:
                        # Check if this is a closing """ at appropriate indent
                        line_stripped = lines[i].strip()
                        line_indent = len(lines[i]) - len(lines[i].lstrip())
                        # Closing should be at same or lower indent than opening
                        if line_indent <= start_indent and line_stripped == '"""':
                            docstring_end_idx = i
                            break

                if docstring_end_idx is None:
                    # Fallback: use original calculation
                    docstring_end_idx = docstring_start_idx + len(docstring.split("\n"))
                    print(f'  WARNING: Could not find closing """ for {func_name}, using fallback')

                # Replace that section with modified docstring
                # Note: The slice lines[docstring_start_idx:docstring_end_idx+1] includes:
                # - The opening """ line with indentation (e.g., '    """content')
                # - All content lines
                # - The closing """ line
                #
                # The modified_docstring from AST doesn't include the opening """,
                # so we need to reconstruct with proper indentation and closing
                indent = " " * start_indent
                replacement = modified_docstring.split("\n")
                # Add opening """ with proper indentation to first content line
                replacement = [indent + '"""' + replacement[0]] + replacement[1:]
                # Add closing """ as a new line
                replacement.append(indent + '"""')
                lines[docstring_start_idx : docstring_end_idx + 1] = replacement

    return "\n".join(lines), updates


def main():
    print(f"Source: {SRC}")

    if not SRC.exists():
        print(f"ERROR: {SRC} not found")
        return 1

    # Backup
    shutil.copy2(SRC, BACKUP)
    print(f"Backup: {BACKUP}")

    content = SRC.read_text()
    original_lines = len(content.split("\n"))

    new_content, updates = process_file(content)

    if updates == 0:
        print("No updates needed")
        BACKUP.unlink()
        return 0

    # Verify syntax
    try:
        ast.parse(new_content)
        print("✅ Syntax check passed")
    except SyntaxError as e:
        print(f"❌ Syntax error: {e}")
        print(f"Line: {e.lineno}")
        print("Restoring backup...")
        shutil.copy2(BACKUP, SRC)
        return 1

    # Write
    SRC.write_text(new_content)
    new_lines = len(new_content.split("\n"))

    print(f"Updated: {updates} parameter hints")
    print(f"Lines: {original_lines} → {new_lines} (+{new_lines - original_lines})")
    return 0


if __name__ == "__main__":
    exit(main())
