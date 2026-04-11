#!/usr/bin/env python3
"""
Example 01: Timeline Navigation

Demonstrates how to:
- Connect to DaVinci Resolve
- List all timelines in the current project
- Get information about the current timeline
- Read clip positions (start, end, duration)
- Get track information

Tested against: DaVinci Resolve Studio 20.3.2.9

Usage:
    python examples/01_timeline_navigation.py

Requirements:
    - DaVinci Resolve running with "External scripting" enabled in Preferences
    - A project open with at least one timeline
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
            print(f"✓ Connected to {resolve.GetProductName()} {resolve.GetVersionString()}")
            return resolve
        else:
            print("✗ Failed to connect to Resolve (is it running?)")
            return None
    except ImportError:
        print("✗ Failed to import DaVinciResolveScript")
        print("  Check that RESOLVE_SCRIPT_API is set correctly")
        return None


def list_timelines(resolve):
    """List all timelines in the current project."""
    pm = resolve.GetProjectManager()
    if not pm:
        print("✗ Failed to get ProjectManager")
        return []
    proj = pm.GetCurrentProject()

    if not proj:
        print("✗ No project open")
        return []

    print(f"\n✓ Project: {proj.GetName()}")

    # Get timeline count
    timeline_count = proj.GetTimelineCount()
    print(f"  Timelines: {timeline_count}")

    timelines = []
    for i in range(1, timeline_count + 1):
        tl = proj.GetTimelineByIndex(i)
        if tl:
            timelines.append(tl)
            print(f"  [{i}] {tl.GetName()} (frames {tl.GetStartFrame()}-{tl.GetEndFrame()})")

    return timelines


def get_current_timeline_info(resolve):
    """Get detailed info about the current timeline."""
    pm = resolve.GetProjectManager()
    if not pm:
        print("✗ Failed to get ProjectManager")
        return
    proj = pm.GetCurrentProject()
    if not proj:
        print("✗ No project open")
        return
    tl = proj.GetCurrentTimeline()

    if not tl:
        print("\n✗ No timeline active")
        return

    print(f"\n✓ Current Timeline: {tl.GetName()}")
    print(f"  Start Frame: {tl.GetStartFrame()}")
    print(f"  End Frame: {tl.GetEndFrame()}")
    print(f"  Timecode: {tl.GetCurrentTimecode()}")

    # Get format settings
    width = tl.GetSetting("timelineResolutionWidth")
    height = tl.GetSetting("timelineResolutionHeight")
    fps = tl.GetSetting("timelineFrameRate")
    print(f"  Resolution: {width}x{height}")
    print(f"  Frame Rate: {fps} fps")


def get_clip_positions(resolve):
    """Read clip positions from the current timeline."""
    pm = resolve.GetProjectManager()
    if not pm:
        print("✗ Failed to get ProjectManager")
        return
    proj = pm.GetCurrentProject()
    if not proj:
        print("✗ No project open")
        return
    tl = proj.GetCurrentTimeline()

    if not tl:
        return

    print("\n✓ Clip Positions (Video Track 1):")

    items = tl.GetItemListInTrack("video", 1)

    if not items:
        print("  (no clips in video track 1)")
        return

    for i, item in enumerate(items):
        start = item.GetStart()
        end = item.GetEnd()
        duration = item.GetDuration()
        name = item.GetName()

        print(f"  [{i + 1}] {name}")
        print(f"      Start: {start} | End: {end} | Duration: {duration}")

        # Get property info (transforms)
        pan = item.GetProperty("Pan")
        zoom = item.GetProperty("ZoomX")
        if pan or zoom:
            print(f"      Pan: {pan}, Zoom: {zoom}")


def get_track_info(resolve):
    """Get information about all tracks."""
    pm = resolve.GetProjectManager()
    if not pm:
        print("✗ Failed to get ProjectManager")
        return
    proj = pm.GetCurrentProject()
    if not proj:
        print("✗ No project open")
        return
    tl = proj.GetCurrentTimeline()

    if not tl:
        return

    print("\n✓ Track Information:")

    for track_type in ["video", "audio", "subtitle"]:
        count = tl.GetTrackCount(track_type)
        if count > 0:
            print(f"  {track_type.capitalize()} tracks: {count}")
            for i in range(1, count + 1):
                name = tl.GetTrackName(track_type, i)
                is_locked = tl.GetIsTrackLocked(track_type, i)
                is_enabled = tl.GetIsTrackEnabled(track_type, i)
                status = "🔒" if is_locked else ("✅" if is_enabled else "❌")
                print(f"    Track {i}: {name} {status}")


if __name__ == "__main__":
    print("=" * 60)
    print("DaVinci Resolve MCP - Timeline Navigation Example")
    print("=" * 60)

    # Connect
    resolve = connect_to_resolve()
    if not resolve:
        sys.exit(1)

    # List all timelines
    timelines = list_timelines(resolve)
    if not timelines:
        print("\nNo timelines found. Create a timeline first in DaVinci Resolve.")
        sys.exit(1)

    # Get current timeline info
    get_current_timeline_info(resolve)

    # Get clip positions
    get_clip_positions(resolve)

    # Get track info
    get_track_info(resolve)

    print("\n" + "=" * 60)
    print("Done!")
