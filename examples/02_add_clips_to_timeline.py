#!/usr/bin/env python3
"""
Example 02: Add Clips to Timeline

Demonstrates how to:
- Navigate the media pool folder structure
- Import media files into the media pool
- Get clips from the media pool
- Append clips to the current timeline

Tested against: DaVinci Resolve Studio 20.3.2.9

Usage:
    python examples/02_add_clips_to_timeline.py

Requirements:
    - DaVinci Resolve running with "External scripting" enabled
    - A project open
    - Optional: path to a media file to import
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


def navigate_media_pool(resolve):
    """Navigate and display the media pool structure."""
    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()

    if not proj:
        print("✗ No project open")
        return None, None

    mp = proj.GetMediaPool()
    if not mp:
        print("✗ Failed to get MediaPool")
        return None, None

    root_folder = mp.GetRootFolder()
    current_folder = mp.GetCurrentFolder()

    print(f"\n✓ Media Pool")
    print(f"  Root: {root_folder.GetName()}")
    print(f"  Current: {current_folder.GetName()}")

    return mp, proj


def list_clips_in_folder(mp):
    """List all clips in the current media pool folder."""
    current_folder = mp.GetCurrentFolder()
    clips = current_folder.GetClipList()

    print(f"\n  Clips in '{current_folder.GetName()}':")

    if not clips:
        print("    (no clips)")
        return []

    for i, clip in enumerate(clips):
        name = clip.GetName()
        duration = clip.GetDuration()
        fps = clip.GetFrameRate()
        print(f"    [{i + 1}] {name} ({duration} frames @ {fps}fps)")

    return clips


def import_media(mp, file_path):
    """Import a media file into the media pool."""
    print(f"\n✓ Importing: {file_path}")

    if not os.path.exists(file_path):
        print(f"  ✗ File not found: {file_path}")
        return None

    # Import using media storage
    imported = mp.ImportMedia([file_path])

    if imported:
        print(f"  ✓ Imported {len(imported)} item(s)")
        return imported
    else:
        print("  ✗ Import failed")
        return None


def add_clip_to_timeline(mp, clip):
    """Add a clip to the end of the current timeline."""
    print(f"\n  Adding '{clip.GetName()}' to timeline...")

    result = mp.AppendToTimeline([clip])

    if result:
        print(f"  ✓ Added successfully")
        # Result is list of TimelineItems
        for item in result:
            print(f"    TimelineItem: {item.GetName()} at frame {item.GetStart()}")
        return result
    else:
        print("  ✗ Failed to add clip")
        return None


def add_multiple_clips_to_timeline(mp, clips):
    """Add multiple clips to the timeline."""
    if not clips:
        print("\nNo clips to add")
        return

    print(f"\n✓ Adding {len(clips)} clip(s) to timeline...")

    result = mp.AppendToTimeline(clips)

    if result:
        print(f"  ✓ Added {len(result)} TimelineItem(s)")
        for item in result:
            print(f"    - {item.GetName()} at frame {item.GetStart()}")
    else:
        print("  ✗ Failed to add clips")


if __name__ == "__main__":
    print("=" * 60)
    print("DaVinci Resolve MCP - Add Clips to Timeline")
    print("=" * 60)

    # Connect
    resolve = connect_to_resolve()
    if not resolve:
        sys.exit(1)

    # Navigate media pool
    mp, proj = navigate_media_pool(resolve)
    if not mp:
        sys.exit(1)

    # List existing clips
    existing_clips = list_clips_in_folder(mp)

    # If a media file path was provided as argument, import it
    if len(sys.argv) > 1:
        media_path = sys.argv[1]
        imported = import_media(mp, media_path)
        if imported:
            # Add imported clips to timeline
            add_multiple_clips_to_timeline(mp, imported)
    else:
        # Add existing clips to timeline
        if existing_clips:
            print("\n" + "-" * 40)
            print("Adding existing clips to timeline...")
            add_multiple_clips_to_timeline(mp, existing_clips[:3])  # First 3 clips
        else:
            print("\nNo clips found. Provide a media file path as argument:")
            print("  python examples/02_add_clips_to_timeline.py /path/to/video.mp4")

    print("\n" + "=" * 60)
    print("Done! Check the Edit page in DaVinci Resolve.")
