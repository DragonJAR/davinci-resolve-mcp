# DaVinci Resolve MCP Server

[![Version](https://img.shields.io/badge/version-2.2.0-blue.svg)](https://github.com/samuelgursky/davinci-resolve-mcp/releases)
[![API Coverage](https://img.shields.io/badge/API%20Coverage-100%25-brightgreen.svg)](#api-coverage)
[![Tools](https://img.shields.io/badge/MCP%20Tools-28%20(356%20full)-blue.svg)](#server-modes)
[![Tested](https://img.shields.io/badge/Live%20Tested-93.3%25-green.svg)](#api-coverage)
[![DaVinci Resolve](https://img.shields.io/badge/DaVinci%20Resolve-18.5+-darkred.svg)](https://www.blackmagicdesign.com/products/davinciresolve)
[![Python](https://img.shields.io/badge/python-3.10--3.12-green.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](https://opensource.org/licenses/MIT)

A Model Context Protocol (MCP) server providing **complete coverage** of DaVinci Resolve Scripting API. Connect AI assistants (Claude, Cursor, Windsurf) to DaVinci Resolve and control your post-production workflow through natural language.

## Quick Start

```bash
# Clone the repository
git clone https://github.com/samuelgursky/davinci-resolve-mcp.git
cd davinci-resolve-mcp

# Run the installer (requires Resolve to be running)
python install.py
```

The universal installer auto-detects your platform, finds your DaVinci Resolve installation, creates a virtual environment, and configures your MCP client — all in one step.

## Installation

### Prerequisites

- **DaVinci Resolve Studio** 18.5+ (macOS, Windows, or Linux) — free edition does not support external scripting
- **Python 3.10–3.12** recommended (3.13+ may have ABI incompatibilities with Resolve's scripting library)
- DaVinci Resolve running with **Preferences > General > "External scripting using"** set to **Local**

### Option A: Interactive Installer (Recommended)

```bash
python install.py                              # Interactive mode
python install.py --clients all                # Configure all clients
python install.py --clients cursor,claude-desktop  # Specific clients
python install.py --clients manual             # Just print config
python install.py --dry-run --clients all      # Preview without writing
python install.py --no-venv --clients cursor   # Skip venv creation
```

### Option B: Manual Setup

Add to your MCP client config. Choose your client format below.

**OpenCode:**
```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "davinci-resolve": {
      "type": "local",
      "command": ["/path/to/python", "/path/to/server.py"],
      "enabled": true,
      "environment": {
        "RESOLVE_SCRIPT_API": "/path/to/resolve/api",
        "PYTHONPATH": "/path/to/resolve/api/Modules"
      }
    }
  }
}
```

**Standard MCP clients (Claude Desktop, Cursor, Windsurf, VS Code, Zed):**
```json
{
  "mcpServers": {
    "davinci-resolve": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/davinci-resolve-mcp/src/server.py"]
    }
  }
}
```

Platform-specific paths:

| Platform | API Path | Library Path |
|----------|----------|-------------|
| macOS | `/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting` | `fusionscript.so` in DaVinci Resolve.app |
| Windows | `C:\ProgramData\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting` | `fusionscript.dll` in Resolve install dir |
| Linux | `/opt/resolve/Developer/Scripting` | `/opt/resolve/libs/Fusion/fusionscript.so` |

### Environment Variables

| Variable | Purpose | Required |
|----------|---------|----------|
| `RESOLVE_SCRIPT_API` | Path to Resolve API directory | Auto-set by installer |
| `PYTHONPATH` | Path to Resolve API Modules | Auto-set by installer |
| `RESOLVE_SCRIPT_LIB` | Path to Resolve library (Windows/Linux) | Auto-set by installer |

## Supported MCP Clients

The installer can automatically configure any of these clients:

| Client | Config Location | Auto-Install |
|--------|----------------|--------------|
| OpenCode | `~/.config/opencode/opencode.json` (global) or `opencode.json` (project root) | ✅ |
| Claude Desktop | `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) | ✅ |
| Claude Code | `.mcp.json` (project root) | ✅ |
| Cursor | `~/.cursor/mcp.json` | ✅ |
| VS Code (Copilot) | `.vscode/mcp.json` (workspace) | ✅ |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` | ✅ |
| Cline | VS Code global storage | ✅ |
| Roo Code | VS Code global storage | ✅ |
| Zed | `~/.config/zed/settings.json` | ✅ |
| Continue | `~/.continue/config.json` | ✅ |
| JetBrains IDEs | Manual (Settings > Tools > AI Assistant > MCP) | ❌ |

You can configure multiple clients at once, or use `--clients manual` to get copy-paste config snippets.

## Server Modes

The MCP server comes in two modes:

| Mode | File | Tools | Use Case |
|------|------|-------|----------|
| **Compound** (default) | `src/server.py` | 28 | Most users — fast, clean, low context usage |
| **Full** | `src/resolve_mcp_server.py` | 356 | Power users who want one tool per API method |

To use the full server:
```bash
python src/server.py --full    # Launch full 356-tool server
# Or point your MCP config directly at src/resolve_mcp_server.py
```

## Tools Overview

### Project Management

**Tools:** `project_manager`, `project_settings`, `media_storage`, `media_pool`, `folder`, `project_manager_folders`, `project_manager_cloud`, `project_manager_database`

Create, open, save, and delete projects. Import/export projects (.drp), archive/restore, manage databases and cloud projects. Browse media storage volumes, import media files, organize folders and clips in the Media Pool.

### Timeline & Editing

**Tools:** `timeline`, `timeline_markers`, `timeline_item`, `timeline_item_markers`, `timeline_item_takes`

Manage timelines (create, delete, duplicate), tracks (add, delete, lock/unlock), and timeline items (delete, link, move). Add markers, manage in/out points, handle takes for multi-cam edits. Export timelines as EDL/XML/AAF.

### Media & Color

**Tools:** `media_pool_item`, `media_pool_item_markers`, `graph`, `color_group`, `timeline_item_color`

Access clip metadata, properties, and markers. Set clip colors and flags. Manage node graphs, LUTs, and cache settings. Create and manage color groups. Apply grades from DRX files, CDL values, and AI tools (Magic Mask, Smart Reframe, Stabilize).

### Fusion

**Tools:** `fusion_comp`, `timeline_item_fusion`

Full Fusion composition node graph API. Add/delete/find nodes, wire connections, set/get parameters, manage keyframes, control undo grouping, set render ranges. Manage Fusion compositions and output cache on timeline items.

### Rendering

**Tools:** `render`, `render_presets`

Render pipeline management: add/delete jobs, start/stop rendering, check status. Manage render formats, codecs, resolutions, and presets. Quick export for fast renders. Import/export render and burn-in presets.

### Other

**Tools:** `resolve_control`, `resolve_constants`, `gallery`, `gallery_stills`, `layout_presets`, `timeline_ai`

App-level operations (get version, switch pages, quit). API constants reference (22 categories, 152 constants). Gallery and still management with export/import. UI layout preset save/load/import/export/delete. AI/ML features: create subtitles from audio, detect scene cuts, analyze Dolby Vision.

## API Coverage

Every non-deprecated method in DaVinci Resolve Scripting API is covered. The default compound server exposes **28 tools** that group related operations by action parameter. The full granular server provides **356 individual tools** for power users.

| Class | Methods | Tools | Description |
|-------|---------|-------|-------------|
| Resolve | 21 | 21 | App control, pages, layout presets, render/burn-in presets, keyframe mode |
| ProjectManager | 25 | 25 | Project CRUD, folders, databases, cloud projects, archive/restore |
| Project | 42 | 42 | Timelines, render pipeline, settings, LUTs, color groups |
| MediaStorage | 9 | 9 | Volumes, file browsing, media import, mattes |
| MediaPool | 27 | 27 | Folders, clips, timelines, metadata, stereo, sync |
| Folder | 8 | 8 | Clip listing, export, transcription |
| MediaPoolItem | 32 | 32 | Metadata, markers, flags, properties, proxy, transcription |
| Timeline | 56 | 56 | Tracks, markers, items, export, generators, titles, stills, stereo |
| TimelineItem | 76 | 76 | Properties, markers, Fusion comps, versions, takes, CDL, AI tools |
| Gallery | 8 | 8 | Albums, stills, power grades |
| GalleryStillAlbum | 6 | 6 | Stills management, import/export, labels |
| Graph | 11 | 22 | Node operations, LUTs, cache, grades (timeline + clip graph variants) |
| ColorGroup | 5 | 10 | Group management, pre/post clip node graphs |
| **Total** | **342** | **356** | |

### Test Results

**93.3% methods tested live** — 319 out of 342 API methods validated against DaVinci Resolve Studio v20.3.2.9 with 100% pass rate. All 22 v20.3 new methods tested and confirmed.

## Configuration

### OpenCode

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "davinci-resolve": {
      "type": "local",
      "command": ["/path/to/venv/bin/python", "/path/to/davinci-resolve-mcp/src/server.py"],
      "enabled": true,
      "environment": {
        "RESOLVE_SCRIPT_API": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting",
        "PYTHONPATH": "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"
      }
    }
  }
}
```

### Claude Desktop

macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "davinci-resolve": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/davinci-resolve-mcp/src/server.py"]
    }
  }
}
```

### Cursor

`~/.cursor/mcp.json`

```json
{
  "mcpServers": {
    "davinci-resolve": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/davinci-resolve-mcp/src/server.py"]
    }
  }
}
```

### VS Code (Copilot)

`.vscode/mcp.json` (workspace root)

```json
{
  "mcpServers": {
    "davinci-resolve": {
      "command": "/path/to/venv/bin/python",
      "args": ["/path/to/davinci-resolve-mcp/src/server.py"]
    }
  }
}
```

### Zed

`~/.config/zed/settings.json`

```json
{
  "lsp": {
    "mcpServers": {
      "davinci-resolve": {
        "command": "/path/to/venv/bin/python",
        "args": ["/path/to/davinci-resolve-mcp/src/server.py"]
      }
    }
  }
}
```

## Usage Examples

Once connected, control DaVinci Resolve through natural language:

```
"What version of DaVinci Resolve is running?"
"List all projects and open the one called 'My Film'"
"Create a new timeline called 'Assembly Cut' and add all clips from media pool"
"Add a blue marker at current playhead position with note 'Review this'"
"Set up a ProRes 422 HQ render for current timeline"
"Export timeline as an EDL"
"Switch to Color page and grab a still"
"Create a Fusion composition on the selected clip"
```

## Development

### Project Structure

```
davinci-resolve-mcp/
├── install.py                    # Universal installer (macOS/Windows/Linux)
├── src/
│   ├── server.py                # Compound MCP server — 28 tools (default)
│   ├── resolve_mcp_server.py    # Full MCP server — 356 tools (power users)
│   └── utils/                   # Platform detection, Resolve connection helpers
├── docs/
│   └── resolve_scripting_api.txt # Official Resolve Scripting API reference
└── examples/                    # Getting started, markers, media, timeline examples
```

### Contributing

We welcome contributions! The following areas especially need help:

**Help Wanted: Untested API Methods**

**5 methods** (1.5%) remain untested against a live DaVinci Resolve instance:

1. **Cloud Project Methods** (4 methods) — Need DaVinci Resolve cloud infrastructure:
   - `ProjectManager.CreateCloudProject`
   - `ProjectManager.LoadCloudProject`
   - `ProjectManager.ImportCloudProject`
   - `ProjectManager.RestoreCloudProject`

2. **HDR Analysis** (1 method) — Needs specific content:
   - `Timeline.AnalyzeDolbyVision` — needs HDR/Dolby Vision content

**How to Contribute**

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-contribution`)
3. Run the existing test suite to ensure nothing breaks
4. Add your test results or fixes
5. Submit a pull request

**Other Contribution Ideas**

- **Platform testing** — Tests run on macOS; Windows and Linux verification welcome
- **Resolve version compatibility** — Test against Resolve 18.x, 19.0, or newer versions
- **Bug reports** — If a tool returns unexpected results on your setup, file an issue
- **Documentation** — Improve examples, add tutorials, translate docs

## Changelog

### v2.2.0 (April 2026)

**Bug Fixes:**
- `get_keyframes`: Fixed crash when GetKeyframeCount returns None (v20 compatibility)
- `get_property`: Fixed returning null when key is empty
- `get_audio`/`set_audio`: Returns clear error — audio properties not supported by Resolve API
- `get_codecs`: Added fallback when format not set
- `get_keyframe_mode`: Added null handling with mode_name mapping

**New Features:**
- `resolve_constants` tool: 22 categories with 152 API constants
- `get_fairlight_presets`, `apply_fairlight_preset`: Fairlight audio preset management
- `get_items_in_track`, `get_item_list_in_track`: Get timeline items (v20.3)
- `set_media_pool_item_name`: Rename media pool items (v20.3)
- `link_full_resolution_media`, `monitor_growing_file`: Proxy and file monitoring (v20.3)
- `get_voice_isolation_state`, `set_voice_isolation_state`: Voice isolation control (v20.3)
- `timeline_item` `list_properties` action: Lists all valid property keys
- `append_to_timeline`, `create_timeline_from_clips`, `import_media`: Enhanced clip control

**Validation:**
- `set_composite`: Validates against 25 known blend modes
- `set_retime`: Validates process and motion_estimation against known values
- `set_crop`: Validates crop values are in [0.0, 1.0] range

### v2.1.0

- **New `fusion_comp` tool** — 20-action tool exposing full Fusion composition node graph API
- **`timeline_item_fusion` cache actions** — added `get_cache_enabled` and `set_cache` actions
- **Fusion node graph reference** — docstring includes common tool IDs (Merge, TextPlus, Background, Transform, ColorCorrector, DeltaKeyer, etc.)

For older versions, see the [releases page](https://github.com/samuelgursky/davinci-resolve-mcp/releases).

## Troubleshooting

### "Not connected to DaVinci Resolve"

- Ensure DaVinci Resolve Studio is **running** (not just installed)
- Check **Preferences > General > "External scripting using"** is set to **Local**
- Verify the installer detected the correct Resolve installation path
- Run `python src/server.py --full` to test connection manually

### "Could not connect after auto-launch"

- First run may take up to 60 seconds for Resolve to launch
- Check that Resolve Studio (not free edition) is installed
- Windows users: Verify Resolve.exe path matches your installation location
- Linux users: Ensure `/opt/resolve/bin/resolve` exists and is executable

### Tools return unexpected results

- Verify Resolve API paths in your MCP client config match your platform (see [Configuration](#configuration))
- Check Resolve version is 18.5+ and Scripting API is available
- Some tools require specific project state (e.g., a timeline must be current for timeline operations)
- AI features (Magic Mask, Smart Reframe) require DaVinci Neural Engine + Color page context

### Python version warnings

- If you see "Python 3.13+ detected" warnings, recreate the virtual environment:
  ```bash
  python install.py --no-venv --clients all
  # Then manually create venv with Python 3.10-3.12
  ```

### Layout preset or render preset errors

- Ensure preset name does not conflict with existing presets
- For render presets: verify preset file is valid and from same Resolve version
- For layout presets: check that Resolve is in Edit page when saving

## Platform Support

| Platform | Status | Resolve Paths Auto-Detected | Notes |
|----------|--------|----------------------------|-------|
| macOS | ✅ Tested | `/Library/Application Support/Blackmagic Design/...` | Primary development and test platform |
| Windows | ✅ Supported | `C:\ProgramData\Blackmagic Design\...` | Community-tested; PRs welcome |
| Linux | ⚠️ Experimental | `/opt/resolve/...` | Should work — testing and feedback welcome |

## Security Considerations

This MCP server controls DaVinci Resolve via its Scripting API. Some tools perform actions that are destructive or interact with the host filesystem:

| Tool | Risk | Mitigation |
|------|------|------------|
| `quit_app` / `restart_app` | Terminates Resolve process — can cause data loss if unsaved changes exist or a render is in progress | MCP clients should require explicit user confirmation before calling these tools. |
| `export_layout_preset` / `import_layout_preset` / `delete_layout_preset` | Read/write/delete files in Resolve layout presets directory | Path traversal protection validates all resolved paths stay within expected presets directory. |
| `save_project` | Creates and removes a temporary `.drp` file in system temp directory | Path is constructed server-side with no LLM-controlled input. |

**Recommendations for MCP client developers:**
- Enable tool-call confirmation prompts for destructive tools (`quit_app`, `restart_app`, `delete_layout_preset`)
 - Do not grant blanket auto-approval to all tools in this server
