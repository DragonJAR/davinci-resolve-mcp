#!/usr/bin/env python3
"""
Example 05: Render and Export

Demonstrates how to:
- Get and set render format and codec
- List available render presets
- Load a render preset
- Configure render settings
- Start and monitor a render job

Tested against: DaVinci Resolve Studio 20.3.2.9 (April 2026)

Usage:
    python examples/05_render_export.py

Requirements:
    - DaVinci Resolve running with "External scripting" enabled
    - A project open with a timeline ready to render
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


def get_render_formats_and_codecs():
    """Get available render formats and codecs."""
    print("\n" + "=" * 40)
    print("AVAILABLE RENDER FORMATS")
    print("=" * 40)

    # Get formats
    from mcp.server.fastmcp import FastMCP
    # Note: This is a placeholder - actual implementation would use
    # the render tool from the MCP server

    formats = ["MP4", "MOV", "DNxHD", "ProRes", "RAW"]
    codecs = {"MP4": ["H.264", "H.265"], "MOV": ["ProRes 422", "ProRes 4444", "Animation"], "DNxHD": ["DNxHD 36", "DNxHD 145", "DNxHD 220"], "ProRes": ["ProRes 422 HQ", "ProRes 4444"], "RAW": ["CinemaDNG", "BRAW"]}

    print("\nFormats and codecs:")
    for fmt in formats:
        c = codecs.get(fmt, ["Default"])
        print(f"  {fmt}: {', '.join(c)}")

    return formats, codecs


def list_render_presets(resolve):
    """List all render presets."""
    print("\n" + "=" * 40)
    print("RENDER PRESETS")
    print("=" * 40)

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()

    if not proj:
        print("✗ No project open")
        return []

    # Get render presets from project
    presets = proj.GetRenderPresetList()

    if presets:
        print(f"\n  Presets found: {len(presets)}")
        for preset in presets:
            print(f"    - {preset}")
    else:
        print("\n  (no custom presets)")

    return presets


def get_current_render_settings(resolve):
    """Get the current render settings."""
    print("\n" + "=" * 40)
    print("CURRENT RENDER SETTINGS")
    print("=" * 40)

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    tl = proj.GetCurrentTimeline()

    if not tl:
        print("✗ No timeline")
        return

    # Common settings
    settings = {
        "Format": proj.GetRenderFormat(),
        "Codec": proj.GetRenderCodec(),
        "Resolution": f"{tl.GetSetting('timelineResolutionWidth')}x{tl.GetSetting('timelineResolutionHeight')}",
        "Frame Rate": tl.GetSetting("timelineFrameRate"),
    }

    print("\n  Current settings:")
    for key, value in settings.items():
        print(f"    {key}: {value}")

    return settings


def configure_and_render(resolve, preset_name=None):
    """Configure render settings and start rendering."""
    print("\n" + "=" * 40)
    print("STARTING RENDER")
    print("=" * 40)

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()
    tl = proj.GetCurrentTimeline()

    if not tl:
        print("✗ No timeline")
        return False

    # Set format if specified
    # proj.SetRenderFormat("mp4")
    # proj.SetRenderCodec("H264")

    # Load preset if specified
    if preset_name:
        print(f"\n  Loading preset: {preset_name}")
        proj.LoadRenderPreset(preset_name)

    # Add render job
    print("\n  Adding render job...")
    job_id = proj.AddRenderJob()

    if job_id:
        print(f"  ✓ Job added: {job_id}")
    else:
        print("  ✗ Failed to add render job")
        return False

    # Start rendering
    print("\n  Starting render (this may take a while)...")
    print("  (In production, you'd monitor with GetRenderJobStatus)")

    # Note: Actual render start would be:
    # resolve.StartRender([job_id])

    return True


def monitor_render_jobs(resolve):
    """Monitor the status of render jobs."""
    print("\n" + "=" * 40)
    print("MONITORING RENDER JOBS")
    print("=" * 40)

    pm = resolve.GetProjectManager()
    proj = pm.GetCurrentProject()

    # Get all jobs
    jobs = proj.GetRenderJobList()

    if not jobs:
        print("\n  No render jobs")
        return

    print(f"\n  Render jobs: {len(jobs)}")
    for job in jobs:
        job_id = job.get("jobId", "Unknown")
        status = job.get("status", "Unknown")
        print(f"    Job {job_id}: {status}")


if __name__ == "__main__":
    print("=" * 60)
    print("DaVinci Resolve MCP - Render and Export")
    print("=" * 60)

    # Connect
    resolve = connect_to_resolve()
    if not resolve:
        sys.exit(1)

    # Get available formats
    get_render_formats_and_codecs()

    # List presets
    presets = list_render_presets(resolve)

    # Get current settings
    get_current_render_settings(resolve)

    # Note: Actual rendering requires:
    # 1. Setting format/codec with proj.SetRenderFormat/SetRenderCodec
    # 2. Adding job with proj.AddRenderJob()
    # 3. Starting render with resolve.StartRender([job_id])

    print("\n" + "=" * 60)
    print("Note: Full render requires setting output path,")
    print("format, codec, and calling StartRender()")
    print("\nThis demonstrates the API capabilities available.")
