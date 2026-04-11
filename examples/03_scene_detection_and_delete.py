#!/usr/bin/env python3
"""
Example 03: Scene Detection and Clip Deletion

Demonstrates how to:
- Detect scene cuts automatically using DetectSceneCuts()
- Delete clips from timeline (with and without ripple)
- Understand the difference between ripple and non-ripple delete

Tested against: DaVinci Resolve Studio 20.3.2.9 (April 2026)

IMPORTANT: This example modifies your timeline. Work on a copy if unsure.

Usage:
    python examples/03_scene_detection_and_delete.py

Requirements:
    - DaVinci Resolve running with "External scripting" enabled
    - A project open with clips on the timeline
"""

import sys
import os

# Add Resolve API Modules to path
RESOLVE_API_PATH = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
if RESOLVE_API_PATH not in sys.path:
    sys.path.insert(0, RESOLVE_API_PATH)


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


def get_timeline_items(resolve):
    """Get all timeline items from video track 1."""
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()

    if not proj:
        print("✗ No project open")
        return None, None, []

    tl = proj.GetCurrentTimeline()
    if not tl:
        print("✗ No timeline active")
        return proj, None, []

    items = tl.GetItemListInTrack("video", 1) or []
    return proj, tl, items


def detect_scene_cuts(tl):
    """Automatically detect and create scene cuts.

    DetectSceneCuts() analyzes the footage and creates cuts at scene boundaries.
    This is useful for jump cuts, dialogue scenes, or action sequences.
    """
    print("\n" + "=" * 40)
    print("SCENE DETECTION")
    print("=" * 40)

    print("\nRunning DetectSceneCuts()...")
    print("(This analyzes footage and creates cuts at scene boundaries)")

    result = tl.DetectSceneCuts()

    if result:
        print("✓ Scene cuts detected and applied")
    else:
        print("✗ Scene detection failed or no cuts found")

    return result


def delete_clip_with_ripple(tl, item):
    """Delete a clip and close the gap (ripple delete).

    Ripple delete removes the clip AND shifts all subsequent clips
    to close the gap. This maintains the timeline's total duration.
    """
    print(f"\nDeleting '{item.GetName()}' with RIPPLE delete...")

    # Store info before deletion
    start = item.GetStart()
    end = item.GetEnd()
    duration = item.GetDuration()

    # Ripple delete: second argument = True
    result = tl.DeleteClips([item], True)

    if result:
        print(f"✓ Deleted frames {start}-{end} (duration: {duration})")
        print("  Timeline closed the gap (ripple)")
    else:
        print("✗ Delete failed")

    return result


def delete_clip_without_ripple(tl, item):
    """Delete a clip but leave the gap (non-ripple delete).

    Non-ripple delete removes the clip but leaves an empty space.
    Subsequent clips remain in their original positions.
    """
    print(f"\nDeleting '{item.GetName()}' WITHOUT ripple...")

    start = item.GetStart()
    end = item.GetEnd()

    # Non-ripple delete: second argument = False (or omitted)
    result = tl.DeleteClips([item], False)

    if result:
        print(f"✓ Deleted frames {start}-{end}")
        print("  Gap left in timeline (non-ripple)")
    else:
        print("✗ Delete failed")

    return result


def list_timeline_items(tl, items, label="Current Timeline"):
    """Display timeline items with their positions."""
    print(f"\n{label}:")
    print("-" * 50)

    if not items:
        print("  (empty)")
        return

    for i, item in enumerate(items):
        start = item.GetStart()
        end = item.GetEnd()
        duration = item.GetDuration()
        print(f"  [{i + 1}] {item.GetName()}")
        print(f"      Frames: {start} → {end} | Duration: {duration}")


if __name__ == "__main__":
    print("=" * 60)
    print("DaVinci Resolve MCP - Scene Detection & Deletion")
    print("=" * 60)
    print("\n⚠️  WARNING: This script MODIFIES your timeline!")
    print("   Work on a copy of your project if unsure.\n")

    # Connect
    resolve = connect_to_resolve()
    if not resolve:
        sys.exit(1)

    # Get timeline items
    proj, tl, items = get_timeline_items(resolve)

    if not tl:
        print("No timeline to work with")
        sys.exit(1)

    # Show current state
    list_timeline_items(tl, items, "Before any operations")

    # Option 1: Detect scene cuts
    # Uncomment to run:
    # detect_scene_cuts(tl)
    # items = tl.GetItemListInTrack("video", 1) or []
    # list_timeline_items(tl, items, "After DetectSceneCuts()")

    # Option 2: Delete with ripple (leaves no gaps)
    # This deletes the first clip with ripple
    if items:
        print("\n" + "=" * 40)
        print("DEMO: Ripple Delete")
        print("=" * 40)

        # Create a backup reference
        first_item = items[0]

        # Delete with ripple
        result = delete_clip_with_ripple(tl, first_item)

        # Refresh and show
        items = tl.GetItemListInTrack("video", 1) or []
        list_timeline_items(tl, items, "After Ripple Delete")

    print("\n" + "=" * 60)
    print("Done!")
    print("\nNote: DetectSceneCuts() is available but not run in this demo.")
    print("Uncomment the detect_scene_cuts() call to enable it.")
