#!/usr/bin/env python3
"""
Example 04: Color Grading Operations

Demonstrates how to:
- Read color node structure from a clip
- Copy grades between clips
- Get and set CDL (Color Decision List) values
- Work with LUTs (Look-Up Tables)
- Manage color versions

Tested against: DaVinci Resolve Studio 20.3.2.9 (April 2026)

Usage:
    python examples/04_color_grading.py

Requirements:
    - DaVinci Resolve running with "External scripting" enabled
    - A project open with clips on the timeline
"""

import os
import sys

# Add Resolve API Modules to path using platform-specific paths
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, "..", "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from src.utils.platform import get_resolve_paths

paths = get_resolve_paths()
RESOLVE_MODULES_PATH = paths["modules_path"]
if RESOLVE_MODULES_PATH not in sys.path:
    sys.path.insert(0, RESOLVE_MODULES_PATH)


def connect_to_resolve():
    """Connect to DaVinci Resolve instance."""
    try:
        import DaVinciResolveScript as dvr

        resolve = dvr.scriptapp("Resolve")
        if resolve:
            print(f"✓ Connected to {resolve.GetProductName()}")
            return resolve
        else:
            print("✗ Failed to connect to Resolve")
            return None
    except ImportError:
        print("✗ Failed to import DaVinciResolveScript")
        return None


def get_timeline_clip(resolve):
    """Get the first clip from video track 1."""
    pm = resolve.GetProjectManager()
    if not pm:
        print("✗ Failed to get ProjectManager")
        return None
    proj = pm.GetCurrentProject()

    if not proj:
        print("✗ No project open")
        return None

    tl = proj.GetCurrentTimeline()
    if not tl:
        print("✗ No timeline active")
        return None

    items = tl.GetItemListInTrack("video", 1)
    if not items:
        print("✗ No clips on video track 1")
        return None

    return items[0]


def read_color_nodes(item):
    """Read the color node structure of a clip."""
    print("\n" + "=" * 40)
    print("COLOR NODE INFO")
    print("=" * 40)

    node_count = item.GetNumNodes()
    print(f"\n  Node count: {node_count}")

    for i in range(1, node_count + 1):
        label = item.GetNodeLabel(i)
        cache = item.GetColorCache(i) if hasattr(item, "GetColorCache") else "N/A"
        print(f"  Node {i}: {label or '(untitled)'} | Cache: {cache}")

    return node_count


def get_cdl_values(item):
    """Get CDL (Color Decision List) values for node 1."""
    print("\n" + "=" * 40)
    print("CDL VALUES (Node 1)")
    print("=" * 40)

    # CDL: Slope, Offset, Power, Saturation
    cdl = item.GetCDL({})

    if cdl:
        print(f"\n  Slope: {cdl.get('Slope', 'N/A')}")
        print(f"  Offset: {cdl.get('Offset', 'N/A')}")
        print(f"  Power: {cdl.get('Power', 'N/A')}")
        print(f"  Saturation: {cdl.get('Saturation', 'N/A')}")
    else:
        print("\n  (no CDL data available)")

    return cdl


def set_cdl_values(item):
    """Set CDL values for node 1 (making the image slightly warmer)."""
    print("\n" + "=" * 40)
    print("SETTING CDL VALUES")
    print("=" * 40)

    cdl = {
        "NodeIndex": 1,
        "Slope": [1.05, 1.0, 0.95],  # Slight red boost, slight blue reduction
        "Offset": [0.02, 0.0, -0.02],  # Warm lift
        "Power": [1.0, 1.0, 1.0],  # No gamma change
        "Saturation": 1.1,  # 10% more saturation
    }

    print("\n  Setting CDL values (warmer, more saturated)...")
    result = item.SetCDL(cdl)

    if result:
        print("  ✓ CDL values applied")
    else:
        print("  ✗ Failed to set CDL values")

    return result


def copy_grade_to_clips(source_item, target_items):
    """Copy the grade from source to multiple target clips."""
    print("\n" + "=" * 40)
    print("COPY GRADE")
    print("=" * 40)

    if not target_items:
        print("\n  No target clips to copy grade to")
        return False

    print(f"\n  Copying grade from '{source_item.GetName()}'")
    print(f"  To {len(target_items)} clip(s):")

    for item in target_items:
        print(f"    - {item.GetName()}")

    result = source_item.CopyGrades(target_items)

    if result:
        print("\n  ✓ Grade copied successfully")
    else:
        print("\n  ✗ Grade copy failed")

    return result


def export_lut_from_clip(item):
    """Export the current grade as a LUT file."""
    print("\n" + "=" * 40)
    print("EXPORT LUT")
    print("=" * 40)

    # LUT export requires the Color page to be active
    # and a still to be grabbed first

    export_path = "/tmp/grade_lut.cube"

    print(f"\n  Exporting to: {export_path}")
    print("  (Format: .cube 33-point)")

    # Export using the clip's ExportLUT method
    result = item.ExportLUT(0, export_path)  # 0 = .cube format

    if result:
        print("  ✓ LUT exported successfully")
        if os.path.exists(export_path):
            size = os.path.getsize(export_path)
            print(f"    File size: {size} bytes")
    else:
        print("  ✗ LUT export failed")
        print("  (Make sure you're on the Color page with a clip selected)")

    return result


def list_color_versions(item):
    """List all saved color versions for a clip."""
    print("\n" + "=" * 40)
    print("COLOR VERSIONS")
    print("=" * 40)

    versions = item.GetVersionNames()

    if versions:
        print(f"\n  Saved versions: {len(versions)}")
        for v in versions:
            print(f"    - {v}")

        current = item.GetCurrentVersion()
        print(f"\n  Current version: {current}")
    else:
        print("\n  (no saved versions)")

    return versions


if __name__ == "__main__":
    print("=" * 60)
    print("DaVinci Resolve MCP - Color Grading Operations")
    print("=" * 60)

    # Connect
    resolve = connect_to_resolve()
    if not resolve:
        sys.exit(1)

    # Get a clip to work with
    item = get_timeline_clip(resolve)
    if not item:
        print("\nNo clip available to work with. Add clips to timeline first.")
        sys.exit(1)

    print(f"\n✓ Working with: {item.GetName()}")

    # Read node info
    read_color_nodes(item)

    # Get CDL values
    get_cdl_values(item)

    # List versions
    list_color_versions(item)

    # Export LUT (requires Color page)
    # Uncomment when on Color page:
    # export_lut_from_clip(item)

    print("\n" + "=" * 60)
    print("Done!")
    print("\nNote: Some operations require the Color page to be active.")
    print("OpenResolvePage('color') can be used to switch pages.")
