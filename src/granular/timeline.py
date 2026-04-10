#!/usr/bin/env python3
"""Granular server — timeline tools."""

# ── Shared mcp server (defined in granular/__init__.py) ───────────
# ── Imports ──────────────────────────────────────────────────────
import logging
import os
import platform
import subprocess
import tempfile
import time
from typing import Any, Dict, List, Optional

from granular import mcp
from src.utils.app_control import (
    dvr_script,
    get_app_state,
)
from src.utils.cloud_operations import (
    get_cloud_project_list,
)
from src.utils.layout_presets import (
    list_layout_presets,
)

# ── Utility imports (extracted from monolithic server) ───────────
from src.utils.object_inspection import (
    inspect_object,
)
from src.utils.project_properties import (
    get_all_project_properties,
    get_color_settings,
    get_project_info,
    get_project_metadata,
    get_project_property,
    get_superscale_settings,
    get_timeline_format_settings,
    set_timeline_format,
)

# ── Shared mcp server (defined in granular/__init__.py) ───────────
# ── Logger ──────────────────────────────────────────────────────
logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────
def _find_clip_by_id(folder, target_id):
    for clip in folder.GetClipList() or []:
        if clip.GetUniqueId() == target_id:
            return clip
    for sub in folder.GetSubFolderList() or []:
        found = _find_clip_by_id(sub, target_id)
        if found:
            return found
    return None


def _find_clips_by_ids(folder, ids_set):
    found = []
    for clip in folder.GetClipList() or []:
        if clip.GetUniqueId() in ids_set:
            found.append(clip)
    for sub in folder.GetSubFolderList() or []:
        found.extend(_find_clips_by_ids(sub, ids_set))
    return found


def _get_mp():
    resolve = get_resolve()
    if resolve is None:
        return None, None, {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return None, None, {"error": "No project currently open"}
    mp = project.GetMediaPool()
    if not mp:
        return project, None, {"error": "Failed to get MediaPool"}
    return project, mp, None


def _get_timeline():
    resolve = get_resolve()
    if resolve is None:
        return None, None, {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return None, None, {"error": "No project currently open"}
    tl = project.GetCurrentTimeline()
    if not tl:
        return project, None, {"error": "No current timeline"}
    return project, tl, None


def _get_timeline_item(track_type="video", track_index=1, item_index=0):
    _, tl, err = _get_timeline()
    if err:
        return None, err
    items = tl.GetItemListInTrack(track_type, track_index)
    if not items or item_index >= len(items):
        return None, {"error": f"No item at index {item_index} on {track_type} track {track_index}"}
    return items[item_index], None


def _launch_resolve():
    """Launch DaVinci Resolve and wait for it to become available."""
    sys_name = platform.system().lower()
    if sys_name == "darwin":
        app_path = "/Applications/DaVinci Resolve/DaVinci Resolve.app"
        if not os.path.exists(app_path):
            return False
        subprocess.Popen(["open", app_path])
    elif sys_name == "windows":
        app_path = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe"
        if not os.path.exists(app_path):
            return False
        subprocess.Popen([app_path])
    elif sys_name == "linux":
        app_path = "/opt/resolve/bin/resolve"
        if not os.path.exists(app_path):
            return False
        subprocess.Popen([app_path])
    else:
        return False
    logger.info("Launched DaVinci Resolve, waiting for it to respond...")
    for i in range(30):
        time.sleep(2)
        if _try_connect():
            logger.info(f"Resolve responded after {(i + 1) * 2}s")
            return True
    logger.warning("Resolve did not respond within 60s after launch")
    return False


def _navigate_to_folder(mp, folder_path):
    root = mp.GetRootFolder()
    if not folder_path or folder_path in ("Master", "/", ""):
        return root
    parts = folder_path.strip("/").split("/")
    if parts[0] == "Master":
        parts = parts[1:]
    current = root
    for part in parts:
        found = False
        for sub in current.GetSubFolderList() or []:
            if sub.GetName() == part:
                current = sub
                found = True
                break
        if not found:
            return None
    return current


def _resolve_safe_dir(path):
    """Redirect sandbox/temp paths that Resolve can't access to ~/Desktop/resolve-stills.

    Covers macOS (/var/folders, /private/var), Linux (/tmp, /var/tmp),
    and Windows (AppData\\Local\\Temp) sandbox temp directories.
    """
    system_temp = tempfile.gettempdir()
    _is_sandbox = False
    if platform.system() == "Darwin":
        _is_sandbox = path.startswith("/var/") or path.startswith("/private/var/")
    elif platform.system() == "Linux":
        _is_sandbox = path.startswith("/tmp") or path.startswith("/var/tmp")
    elif platform.system() == "Windows":
        try:
            _is_sandbox = os.path.commonpath([os.path.abspath(path), os.path.abspath(system_temp)]) == os.path.abspath(system_temp)
        except ValueError:
            _is_sandbox = False
    if _is_sandbox:
        return os.path.join(os.path.expanduser("~"), "Documents", "resolve-stills")
    return path


def _serialize_value(value):
    """Helper to serialize Resolve API objects to JSON-safe values."""
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {k: _serialize_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize_value(v) for v in value]
    # Resolve API object — return string representation
    return str(value)


def _try_connect():
    """Attempt to connect to Resolve once. Returns resolve object or None."""
    global resolve
    try:
        resolve = dvr_script.scriptapp("Resolve")
        if resolve:
            logger.info(f"Connected: {resolve.GetProductName()} {resolve.GetVersionString()}")
        return resolve
    except Exception as e:
        logger.error(f"Connection error: {e}")
        resolve = None
        return None


def _validate_path(user_path: str) -> str:
    """Validate that user_path doesn't contain path traversal."""
    if ".." in user_path:
        raise ValueError(f"Path traversal detected in: {user_path}")
    return os.path.realpath(user_path)


def find_clip_by_id(folder, target_id):
    for clip in folder.GetClipList() or []:
        if clip.GetUniqueId() == target_id:
            return clip
    for sub in folder.GetSubFolderList() or []:
        found = find_clip_by_id(sub, target_id)
        if found:
            return found
    return None


def get_all_media_pool_clips(media_pool):
    """Get all clips from media pool recursively including subfolders."""
    clips = []
    root_folder = media_pool.GetRootFolder()

    def process_folder(folder):
        folder_clips = folder.GetClipList()
        if folder_clips:
            clips.extend(folder_clips)

        sub_folders = folder.GetSubFolderList()
        for sub_folder in sub_folders:
            process_folder(sub_folder)

    process_folder(root_folder)
    return clips


def get_all_media_pool_folders(media_pool):
    """Get all folders from media pool recursively."""
    folders = []
    root_folder = media_pool.GetRootFolder()

    def process_folder(folder):
        folders.append(folder)

        sub_folders = folder.GetSubFolderList()
        for sub_folder in sub_folders:
            process_folder(sub_folder)

    process_folder(root_folder)
    return folders


def get_app_state_endpoint() -> Dict[str, Any]:
    """Get DaVinci Resolve application state information."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve", "connected": False}

    return get_app_state(resolve)


def get_cache_settings() -> Dict[str, Any]:
    """Get current cache settings from the project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    try:
        # Get all cache-related settings
        settings = {}
        cache_keys = [
            "CacheMode",
            "CacheClipMode",
            "OptimizedMediaMode",
            "ProxyMode",
            "ProxyQuality",
            "TimelineCacheMode",
            "LocalCachePath",
            "NetworkCachePath",
        ]

        for key in cache_keys:
            value = current_project.GetSetting(key)
            settings[key] = value

        return settings
    except Exception as e:
        return {"error": f"Failed to get cache settings: {str(e)}"}


def get_cloud_projects() -> Dict[str, Any]:
    """Get list of available cloud projects."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve", "success": False}

    return get_cloud_project_list(resolve)


def get_color_presets() -> List[Dict[str, Any]]:
    """Get all available color presets in the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return [{"error": "No project currently open"}]

    # Switch to color page to access presets
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return [{"error": "Failed to get gallery"}]

        # Get all albums
        albums = gallery.GetAlbums()
        if not albums:
            return [{"info": "No albums found in gallery"}]

        result = []
        for album in albums:
            # Get stills in the album
            stills = album.GetStills()
            album_info = {"name": album.GetName(), "stills": []}

            if stills:
                for still in stills:
                    still_info = {
                        "id": still.GetUniqueId(),
                        "label": still.GetLabel(),
                        "timecode": still.GetTimecode(),
                        "isGrabbed": still.IsGrabbed(),
                    }
                    album_info["stills"].append(still_info)

            result.append(album_info)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        return result

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return [{"error": f"Error retrieving color presets: {str(e)}"}]


def get_color_settings_endpoint() -> Dict[str, Any]:
    """Get color science and color space settings for the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_color_settings(current_project)


def get_color_wheel_params(node_index: int = None) -> Dict[str, Any]:
    """Get color wheel parameters for a specific node.

    Args:
        node_index: Index of the node to get color wheels from (uses current node if None)
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def get_current_color_node() -> Dict[str, Any]:
    """Get information about the current node in the color page."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def get_current_page() -> str:
    """Get the current page open in DaVinci Resolve (Edit, Color, Fusion, etc.)."""
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"
    return resolve.GetCurrentPage()


def get_current_project():
    """Get current project with lazy connection and null guards."""
    pm = get_project_manager()
    if not pm:
        return None, None
    proj = pm.GetCurrentProject()
    return pm, proj


def get_current_project_name() -> str:
    """Get the name of the currently open project."""
    pm, current_project = get_current_project()
    if not current_project:
        return "No project currently open"

    return current_project.GetName()


def get_current_timeline() -> Dict[str, Any]:
    """Get information about the current timeline."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    # Get basic timeline information
    result = {
        "name": current_timeline.GetName(),
        "fps": current_timeline.GetSetting("timelineFrameRate"),
        "resolution": {
            "width": current_timeline.GetSetting("timelineResolutionWidth"),
            "height": current_timeline.GetSetting("timelineResolutionHeight"),
        },
        "duration": current_timeline.GetEndFrame() - current_timeline.GetStartFrame() + 1,
    }

    return result


def get_layout_presets() -> List[Dict[str, Any]]:
    """Get all available layout presets for DaVinci Resolve."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}

    return list_layout_presets(layout_type="ui")


def get_lut_formats() -> Dict[str, Any]:
    """Get available LUT export formats and sizes."""
    formats = {
        "formats": [
            {
                "name": "Cube",
                "extension": ".cube",
                "description": "Industry standard LUT format supported by most applications",
            },
            {
                "name": "Davinci",
                "extension": ".ilut",
                "description": "DaVinci Resolve's native LUT format",
            },
            {
                "name": "3dl",
                "extension": ".3dl",
                "description": "ASSIMILATE SCRATCH and some Autodesk applications",
            },
            {
                "name": "Panasonic",
                "extension": ".vlut",
                "description": "Panasonic VariCam and other Panasonic cameras",
            },
        ],
        "sizes": [
            {
                "name": "17Point",
                "description": "Smaller file size, less precision (17x17x17)",
            },
            {
                "name": "33Point",
                "description": "Standard size with good balance of precision and file size (33x33x33)",
            },
            {
                "name": "65Point",
                "description": "Highest precision but larger file size (65x65x65)",
            },
        ],
    }
    return formats


def get_media_pool_bin_contents(bin_name: str) -> List[Dict[str, Any]]:
    """Get contents of a specific bin/folder in the media pool.

    Args:
        bin_name: The name of the bin to get contents from. Use 'Master' for the root folder.
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def get_project_info_endpoint() -> Dict[str, Any]:
    """Get comprehensive information about the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_project_info(current_project)


def get_project_manager():
    """Get ProjectManager with lazy connection and null guard."""
    r = get_resolve()
    if not r:
        return None
    pm = r.GetProjectManager()
    return pm


def get_project_metadata_endpoint() -> Dict[str, Any]:
    """Get metadata for the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_project_metadata(current_project)


def get_project_properties_endpoint() -> Dict[str, Any]:
    """Get all project properties for the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_all_project_properties(current_project)


def get_project_property_endpoint(property_name: str) -> Dict[str, Any]:
    """Get a specific project property value.

    Args:
        property_name: Name of the property to get
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    value = get_project_property(current_project, property_name)
    return {property_name: value}


def get_project_setting(setting_name: str) -> Dict[str, Any]:
    """Get a specific project setting by name.

    Args:
        setting_name: The specific setting to retrieve.
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    try:
        # Get specific setting
        value = current_project.GetSetting(setting_name)
        return {setting_name: value}
    except Exception as e:
        return {"error": f"Failed to get project setting '{setting_name}': {str(e)}"}


def get_project_settings() -> Dict[str, Any]:
    """Get all project settings from the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    try:
        # Get all settings
        return current_project.GetSetting("")
    except Exception as e:
        return {"error": f"Failed to get project settings: {str(e)}"}


def get_render_presets() -> List[Dict[str, Any]]:
    """Get all available render presets in the current project."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def get_render_queue_status() -> Dict[str, Any]:
    """Get the status of jobs in the render queue."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def get_resolve():
    """Lazy connection to Resolve — connects on first tool call, auto-launches if needed."""
    global resolve
    if resolve is not None:
        return resolve
    if _try_connect():
        return resolve
    logger.info("Resolve not running, attempting to launch automatically...")
    _launch_resolve()
    return resolve


def get_resolve_version() -> str:
    """Get DaVinci Resolve version information."""
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"
    return f"{resolve.GetProductName()} {resolve.GetVersionString()}"


def get_superscale_settings_endpoint() -> Dict[str, Any]:
    """Get SuperScale settings for the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_superscale_settings(current_project)


def get_timeline_format() -> Dict[str, Any]:
    """Get timeline format settings for the current project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return get_timeline_format_settings(current_project)


def get_timeline_item_keyframes(timeline_item_id: str, property_name: str) -> Dict[str, Any]:
    """Get keyframes for a specific timeline item by ID.

    Args:
        timeline_item_id: The ID of the timeline item to get keyframes for
        property_name: Optional property name to filter keyframes (e.g., 'Pan', 'ZoomX')
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")
        audio_track_count = current_timeline.GetTrackCount("audio")

        timeline_item = None

        # Search video tracks
        for track_index in range(1, video_track_count + 1):
            items = current_timeline.GetItemListInTrack("video", track_index)
            if items:
                for item in items:
                    if str(item.GetUniqueId()) == timeline_item_id:
                        timeline_item = item
                        break
            if timeline_item:
                break

        # If not found, search audio tracks
        if not timeline_item:
            for track_index in range(1, audio_track_count + 1):
                items = current_timeline.GetItemListInTrack("audio", track_index)
                if items:
                    for item in items:
                        if str(item.GetUniqueId()) == timeline_item_id:
                            timeline_item = item
                            break
                if timeline_item:
                    break

        if not timeline_item:
            return {"error": f"Timeline item with ID '{timeline_item_id}' not found"}

        # Get all keyframeable properties for this item
        keyframeable_properties = []
        keyframes = {}

        # Common keyframeable properties for video items
        video_properties = [
            "Pan",
            "Tilt",
            "ZoomX",
            "ZoomY",
            "Rotation",
            "AnchorPointX",
            "AnchorPointY",
            "Pitch",
            "Yaw",
            "Opacity",
            "CropLeft",
            "CropRight",
            "CropTop",
            "CropBottom",
        ]

        # Audio-specific keyframeable properties
        audio_properties = ["Volume", "Pan"]

        # Check if it's a video item
        if timeline_item.GetType() == "Video":
            # Check each property to see if it has keyframes
            for prop in video_properties:
                if (timeline_item.GetKeyframeCount(prop) or 0) > 0:
                    keyframeable_properties.append(prop)

                    # Get all keyframes for this property
                    keyframes[prop] = []
                    keyframe_count = timeline_item.GetKeyframeCount(prop) or 0

                    for i in range(keyframe_count):
                        # Get the frame position and value of the keyframe
                        frame_pos = timeline_item.GetKeyframeAtIndex(prop, i)["frame"]
                        value = timeline_item.GetPropertyAtKeyframeIndex(prop, i)

                        keyframes[prop].append({"frame": frame_pos, "value": value})

        # Check if it has audio properties (could be video with audio or audio-only)
        if timeline_item.GetType() == "Audio" or timeline_item.GetMediaType() == "Audio":
            # Check each audio property for keyframes
            for prop in audio_properties:
                if (timeline_item.GetKeyframeCount(prop) or 0) > 0:
                    keyframeable_properties.append(prop)

                    # Get all keyframes for this property
                    keyframes[prop] = []
                    keyframe_count = timeline_item.GetKeyframeCount(prop) or 0

                    for i in range(keyframe_count):
                        # Get the frame position and value of the keyframe
                        frame_pos = timeline_item.GetKeyframeAtIndex(prop, i)["frame"]
                        value = timeline_item.GetPropertyAtKeyframeIndex(prop, i)

                        keyframes[prop].append({"frame": frame_pos, "value": value})

        # Filter by property_name if specified
        if property_name:
            if property_name in keyframes:
                return {
                    "item_id": timeline_item_id,
                    "item_name": timeline_item.GetName(),
                    "properties": [property_name],
                    "keyframes": {property_name: keyframes[property_name]},
                }
            else:
                return {
                    "item_id": timeline_item_id,
                    "item_name": timeline_item.GetName(),
                    "properties": [],
                    "keyframes": {},
                }

        # Return all keyframes
        return {
            "item_id": timeline_item_id,
            "item_name": timeline_item.GetName(),
            "properties": keyframeable_properties,
            "keyframes": keyframes,
        }

    except Exception as e:
        return {"error": f"Error getting timeline item keyframes: {str(e)}"}


def get_timeline_item_properties(timeline_item_id: str) -> Dict[str, Any]:
    """Get properties of a specific timeline item by ID.

    Args:
        timeline_item_id: The ID of the timeline item to get properties for
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    try:
        # Find the timeline item by ID
        # We'll need to get all items from all tracks and check their IDs
        video_track_count = current_timeline.GetTrackCount("video")
        audio_track_count = current_timeline.GetTrackCount("audio")

        timeline_item = None

        # Search video tracks
        for track_index in range(1, video_track_count + 1):
            items = current_timeline.GetItemListInTrack("video", track_index)
            if items:
                for item in items:
                    if str(item.GetUniqueId()) == timeline_item_id:
                        timeline_item = item
                        break
            if timeline_item:
                break

        # If not found, search audio tracks
        if not timeline_item:
            for track_index in range(1, audio_track_count + 1):
                items = current_timeline.GetItemListInTrack("audio", track_index)
                if items:
                    for item in items:
                        if str(item.GetUniqueId()) == timeline_item_id:
                            timeline_item = item
                            break
                if timeline_item:
                    break

        if not timeline_item:
            return {"error": f"Timeline item with ID '{timeline_item_id}' not found"}

        # Get basic properties
        properties = {
            "id": timeline_item_id,
            "name": timeline_item.GetName(),
            "type": timeline_item.GetType(),
            "start_frame": timeline_item.GetStart(),
            "end_frame": timeline_item.GetEnd(),
            "duration": timeline_item.GetDuration(),
        }

        # Get additional properties if it's a video item
        if timeline_item.GetType() == "Video":
            # Transform properties
            properties["transform"] = {
                "position": {
                    "x": timeline_item.GetProperty("Pan"),
                    "y": timeline_item.GetProperty("Tilt"),
                },
                "zoom": timeline_item.GetProperty("ZoomX"),  # ZoomX/ZoomY can be different for non-uniform scaling
                "zoom_x": timeline_item.GetProperty("ZoomX"),
                "zoom_y": timeline_item.GetProperty("ZoomY"),
                "rotation": timeline_item.GetProperty("Rotation"),
                "anchor_point": {
                    "x": timeline_item.GetProperty("AnchorPointX"),
                    "y": timeline_item.GetProperty("AnchorPointY"),
                },
                "pitch": timeline_item.GetProperty("Pitch"),
                "yaw": timeline_item.GetProperty("Yaw"),
            }

            # Crop properties
            properties["crop"] = {
                "left": timeline_item.GetProperty("CropLeft"),
                "right": timeline_item.GetProperty("CropRight"),
                "top": timeline_item.GetProperty("CropTop"),
                "bottom": timeline_item.GetProperty("CropBottom"),
            }

            # Composite properties
            properties["composite"] = {
                "mode": timeline_item.GetProperty("CompositeMode"),
                "opacity": timeline_item.GetProperty("Opacity"),
            }

            # Dynamic zoom properties
            properties["dynamic_zoom"] = {
                "enabled": timeline_item.GetProperty("DynamicZoomEnable"),
                "mode": timeline_item.GetProperty("DynamicZoomMode"),
            }

            # Retime properties
            properties["retime"] = {
                "speed": timeline_item.GetProperty("Speed"),
                "process": timeline_item.GetProperty("RetimeProcess"),
            }

            # Stabilization properties
            properties["stabilization"] = {
                "enabled": timeline_item.GetProperty("StabilizationEnable"),
                "method": timeline_item.GetProperty("StabilizationMethod"),
                "strength": timeline_item.GetProperty("StabilizationStrength"),
            }

        # Audio-specific properties
        if timeline_item.GetType() == "Audio" or timeline_item.GetMediaType() == "Audio":
            properties["audio"] = {
                "volume": timeline_item.GetProperty("Volume"),
                "pan": timeline_item.GetProperty("Pan"),
                "eq_enabled": timeline_item.GetProperty("EQEnable"),
                "normalize_enabled": timeline_item.GetProperty("NormalizeEnable"),
                "normalize_level": timeline_item.GetProperty("NormalizeLevel"),
            }

        return properties

    except Exception as e:
        return {"error": f"Error getting timeline item properties: {str(e)}"}


def get_timeline_items() -> List[Dict[str, Any]]:
    """Get all items in the current timeline with their IDs and basic properties."""
    pm, current_project = get_current_project()
    if not current_project:
        return [{"error": "No project currently open"}]

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return [{"error": "No timeline currently active"}]

    try:
        # Get all tracks in the timeline
        video_track_count = current_timeline.GetTrackCount("video")
        audio_track_count = current_timeline.GetTrackCount("audio")

        items = []

        # Process video tracks
        for track_index in range(1, video_track_count + 1):
            track_items = current_timeline.GetItemListInTrack("video", track_index)
            if track_items:
                for item in track_items:
                    items.append(
                        {
                            "id": str(item.GetUniqueId()),
                            "name": item.GetName(),
                            "type": "video",
                            "track": track_index,
                            "start_frame": item.GetStart(),
                            "end_frame": item.GetEnd(),
                            "duration": item.GetDuration(),
                        }
                    )

        # Process audio tracks
        for track_index in range(1, audio_track_count + 1):
            track_items = current_timeline.GetItemListInTrack("audio", track_index)
            if track_items:
                for item in track_items:
                    items.append(
                        {
                            "id": str(item.GetUniqueId()),
                            "name": item.GetName(),
                            "type": "audio",
                            "track": track_index,
                            "start_frame": item.GetStart(),
                            "end_frame": item.GetEnd(),
                            "duration": item.GetDuration(),
                        }
                    )

        if not items:
            return [{"info": "No items found in the current timeline"}]

        return items
    except Exception as e:
        return [{"error": f"Error listing timeline items: {str(e)}"}]


def get_timeline_tracks(timeline_name: str = None) -> Dict[str, Any]:
    """Get the track structure of a timeline.

    Args:
        timeline_name: Optional name of the timeline to get tracks from. Uses current timeline if None.
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def inspect_current_project_object() -> Dict[str, Any]:
    """Inspect the current project object and return its methods and properties."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return inspect_object(current_project)


def inspect_current_timeline_object() -> Dict[str, Any]:
    """Inspect the current timeline object and return its methods and properties."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    return inspect_object(current_timeline)


def inspect_media_pool_object() -> Dict[str, Any]:
    """Inspect the media pool object and return its methods and properties."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return {"error": "Failed to get Media Pool"}

    return inspect_object(media_pool)


def inspect_project_manager_object() -> Dict[str, Any]:
    """Inspect the project manager object and return its methods and properties."""
    project_manager = get_project_manager()
    if not project_manager:
        return {"error": "Failed to get Project Manager"}

    return inspect_object(project_manager)


def inspect_resolve_object() -> Dict[str, Any]:
    """Inspect the main resolve object and return its methods and properties."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}

    return inspect_object(resolve)


def list_media_pool_bins() -> List[Dict[str, Any]]:
    """List all bins/folders in the media pool."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


def list_media_pool_clips() -> List[Dict[str, Any]]:
    """List all clips in the root folder of the media pool."""
    pm, current_project = get_current_project()
    if not current_project:
        return [{"error": "No project currently open"}]

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return [{"error": "Failed to get Media Pool"}]

    root_folder = media_pool.GetRootFolder()
    if not root_folder:
        return [{"error": "Failed to get root folder"}]

    clips = root_folder.GetClipList()
    if not clips:
        return [{"info": "No clips found in the root folder"}]

    # Return a simplified list with basic clip info
    result = []
    for clip in clips:
        result.append(
            {
                "name": clip.GetName(),
                "duration": clip.GetDuration(),
                "fps": clip.GetClipProperty("FPS"),
            }
        )

    return result


def list_projects() -> List[str]:
    """List all available projects in the current database."""
    project_manager = get_project_manager()
    if not project_manager:
        return ["Error: Failed to get Project Manager"]

    projects = project_manager.GetProjectListInCurrentFolder()

    # Filter out any empty strings that might be in the list
    return [p for p in projects if p]


def list_timeline_clips() -> List[Dict[str, Any]]:
    """List all clips in the current timeline."""
    pm, current_project = get_current_project()
    if not current_project:
        return [{"error": "No project currently open"}]

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return [{"error": "No timeline currently active"}]

    try:
        # Get all tracks in the timeline
        # Video tracks are 1-based index (1 is first track)
        video_track_count = current_timeline.GetTrackCount("video")
        audio_track_count = current_timeline.GetTrackCount("audio")

        clips = []

        # Process video tracks
        for track_index in range(1, video_track_count + 1):
            track_items = current_timeline.GetItemListInTrack("video", track_index)
            if track_items:
                for item in track_items:
                    clips.append(
                        {
                            "name": item.GetName(),
                            "type": "video",
                            "track": track_index,
                            "start_frame": item.GetStart(),
                            "end_frame": item.GetEnd(),
                            "duration": item.GetDuration(),
                        }
                    )

        # Process audio tracks
        for track_index in range(1, audio_track_count + 1):
            track_items = current_timeline.GetItemListInTrack("audio", track_index)
            if track_items:
                for item in track_items:
                    clips.append(
                        {
                            "name": item.GetName(),
                            "type": "audio",
                            "track": track_index,
                            "start_frame": item.GetStart(),
                            "end_frame": item.GetEnd(),
                            "duration": item.GetDuration(),
                        }
                    )

        if not clips:
            return [{"info": "No clips found in the current timeline"}]

        return clips
    except Exception as e:
        return [{"error": f"Error listing timeline clips: {str(e)}"}]


def list_timelines() -> List[str]:
    """List all timelines in the current project."""
    logger.info("Received request to list timelines")

    if resolve is None:
        logger.error("Not connected to DaVinci Resolve")
        return ["Error: Not connected to DaVinci Resolve"]

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        logger.error("Failed to get Project Manager")
        return ["Error: Failed to get Project Manager"]

    current_project = project_manager.GetCurrentProject()
    if not current_project:
        logger.error("No project currently open")
        return ["Error: No project currently open"]

    timeline_count = current_project.GetTimelineCount()
    logger.info(f"Timeline count: {timeline_count}")

    timelines = []

    for i in range(1, timeline_count + 1):
        timeline = current_project.GetTimelineByIndex(i)
        if timeline:
            timeline_name = timeline.GetName()
            timelines.append(timeline_name)
            logger.info(f"Found timeline {i}: {timeline_name}")

    if not timelines:
        logger.info("No timelines found in the current project")
        return ["No timelines found in the current project"]

    logger.info(f"Returning {len(timelines)} timelines: {', '.join(timelines)}")
    return timelines


# ── Tools ────────────────────────────────────────────────────────
@mcp.tool()
def add_clip_to_timeline(clip_name: str, timeline_name: str = None) -> str:
    """Add a media pool clip to the timeline.

    Args:
    clip_name: Name of the clip in the media pool
    timeline_name: Optional timeline to target (uses current if not specified)
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def add_marker(frame: int = None, color: str = "Blue", note: str = "") -> str:
    """Add a marker at the specified frame in the current timeline.

        Args:
        frame: The frame number to add marker at (defaults to current position if None)
    color: The marker color (Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream)
        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    note: Text note to add to marker
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def create_empty_timeline(
    name: str,
    frame_rate: str = None,
    resolution_width: int = None,
    resolution_height: int = None,
    start_timecode: str = None,
    video_tracks: int = None,
    audio_tracks: int = None,
) -> str:
    """Create a new timeline with the given name and custom settings.

    Args:
    name: The name for the new timeline
    frame_rate: Optional frame rate (e.g. "24", "29.97", "30", "60")
    resolution_width: Optional width in pixels (e.g. 1920)
    resolution_height: Optional height in pixels (e.g. 1080)
    start_timecode: Optional start timecode (e.g. "01:00:00:00")
    video_tracks: Optional number of video tracks (Default is project setting)
    audio_tracks: Optional number of audio tracks (Default is project setting)
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def create_timeline_from_clips(name: str, clip_ids: List[str] = None, clip_infos: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Create a new timeline from specified media pool clips.

    Args:
    name: Name for the new timeline.
    clip_ids: List of MediaPoolItem unique IDs to include. If None, uses selected clips.
    clip_infos: Optional list of clip info dicts for advanced control.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip_infos = clip_infos or []
    clip_ids = clip_ids or []
    if clip_infos:
        clips = clip_infos
    else:
        root = mp.GetRootFolder()
        clips = []
        for cid in clip_ids:
            clip = _find_clip_by_id(root, cid)
            if clip:
                clips.append(clip)
            else:
                return {"error": f"Clip not found: {cid}"}
    if not clips:
        return {"error": "No clips specified and none selected in media pool"}
    tl = mp.CreateTimelineFromClips(name, clips)
    if tl:
        return {
            "success": True,
            "timeline_name": tl.GetName(),
            "timeline_id": tl.GetUniqueId(),
        }
    return {"success": False, "error": "Failed to create timeline from clips"}


@mcp.tool()
def delete_timeline(name: str) -> str:
    """Delete a timeline by name.

    Args:
    name: The name of the timeline to delete
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def get_item_list_in_track(track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get item list in a specific track.

        Args:
        track_type: The type of track ('video', 'audio', 'subtitle')
        Valid: "video", "audio", "subtitle"
    track_index: The index of the track (1-based index, defaults to 1)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    try:
        items = current_timeline.GetItemListInTrack(track_type, track_index)
        return {"items": _serialize_value(items)}
    except Exception as e:
        return {"error": f"Failed to get item list in track: {str(e)}"}


@mcp.tool()
def get_items_in_track(track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get all items in a specific track.

        Args:
        track_type: The type of track ('video', 'audio', 'subtitle')
        Valid: "video", "audio", "subtitle"
    track_index: The index of the track (1-based index, defaults to 1)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    try:
        items = current_timeline.GetItemsInTrack(track_type, track_index)
        return {"items": _serialize_value(items)}
    except Exception as e:
        return {"error": f"Failed to get items in track: {str(e)}"}


@mcp.tool()
def get_timeline_by_index(index: int) -> Dict[str, Any]:
    """Get a timeline by its 1-based index.

    Args:
    index: 1-based timeline index.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    tl = project.GetTimelineByIndex(index)
    if tl:
        return {
            "name": tl.GetName(),
            "start_frame": tl.GetStartFrame(),
            "end_frame": tl.GetEndFrame(),
            "unique_id": tl.GetUniqueId(),
        }
    return {"error": f"No timeline at index {index}"}


@mcp.tool()
def import_timeline_from_file(file_path: str, import_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Import a timeline from a file (AAF, EDL, XML, FCPXML, DRT, ADL, OTIO).

    Args:
    file_path: Absolute path to the timeline file.
    import_options: Optional dict of import options.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    if import_options:
        tl = mp.ImportTimelineFromFile(file_path, import_options)
    else:
        tl = mp.ImportTimelineFromFile(file_path)
    if tl:
        return {
            "success": True,
            "timeline_name": tl.GetName(),
            "unique_id": tl.GetUniqueId(),
        }
    return {"success": False, "error": f"Failed to import timeline from '{file_path}'"}


@mcp.tool()
def list_timelines_tool() -> List[str]:
    """List all timelines in the current project as a tool."""
    logger.info("Received request to list timelines via tool")
    return list_timelines()


@mcp.tool()
def set_current_timeline(name: str) -> str:
    """Switch to a timeline by name.

    Args:
    name: The name of the timeline to set as current
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    if not name:
        return "Error: Timeline name cannot be empty"

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        return "Error: Failed to get Project Manager"

    current_project = project_manager.GetCurrentProject()
    if not current_project:
        return "Error: No project currently open"

    # Find the timeline by name
    timeline_count = current_project.GetTimelineCount()
    for i in range(1, timeline_count + 1):
        timeline = current_project.GetTimelineByIndex(i)
        if timeline and timeline.GetName() == name:
            result = current_project.SetCurrentTimeline(timeline)
            if result:
                return f"Successfully switched to timeline '{name}'"
            else:
                return f"Failed to switch to timeline '{name}'"

    return f"Error: Timeline '{name}' not found"


@mcp.tool()
def set_timeline_format_tool(width: int, height: int, frame_rate: float, interlaced: bool = False) -> str:
    """Set timeline format (resolution and frame rate).

    Args:
    width: Timeline width in pixels
    height: Timeline height in pixels
    frame_rate: Timeline frame rate
    interlaced: Whether the timeline should use interlaced processing
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    result = set_timeline_format(current_project, width, height, frame_rate, interlaced)

    if result:
        interlace_status = "interlaced" if interlaced else "progressive"
        return f"Successfully set timeline format to {width}x{height} at {frame_rate} fps ({interlace_status})"
    else:
        return "Failed to set timeline format"


@mcp.tool()
def set_timeline_setting(setting_name: str, setting_value: str) -> Dict[str, Any]:
    """Set a timeline setting value.

    Args:
    setting_name: Name of the timeline setting to set (e.g. 'useCustomSettings', 'timelineFrameRate',
                  'timelineResolutionWidth', 'timelineResolutionHeight', 'timelineOutputResolutionWidth',
                  'timelineOutputResolutionHeight', 'colorSpaceTimeline', 'colorSpaceOutput').
    setting_value: Value to set for the setting (string).
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetSetting(setting_name, setting_value)
    return {
        "success": bool(result),
        "setting_name": setting_name,
        "setting_value": setting_value,
    }


@mcp.tool()
def ti_copy_grades(
    target_item_indices: List[int],
    track_type: str = "video",
    track_index: int = 1,
    source_item_index: int = 0,
) -> Dict[str, Any]:
    """Copy grades from one timeline item to others.

        Args:
        target_item_indices: List of 0-based indices of target items.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    source_item_index: 0-based source item index. Default: 0.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    items = tl.GetItemListInTrack(track_type, track_index)
    if not items:
        return {"error": "No items in track"}
    source = items[source_item_index] if source_item_index < len(items) else None
    if not source:
        return {"error": "Source item not found"}
    targets = [items[i] for i in target_item_indices if i < len(items)]
    if not targets:
        return {"error": "No target items found"}
    result = source.CopyGrades(targets)
    return {"success": bool(result)}


@mcp.tool()
def timeline_add_marker(
    frame_id: int,
    color: str,
    name: str,
    note: str = "",
    duration: int = 1,
    custom_data: str = "",
) -> Dict[str, Any]:
    """Add a marker to the current timeline.

        Args:
        frame_id: Frame number for the marker.
    color: Marker color (Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream).
        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    name: Marker name.
    note: Marker note. Default: empty.
    duration: Duration in frames. Default: 1.
    custom_data: Custom data string. Default: empty.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.AddMarker(frame_id, color, name, note, duration, custom_data)
    return {"success": bool(result)}


@mcp.tool()
def timeline_add_track(track_type: str, sub_track_type: str = "", new_track_options: Dict[str, Any] = None) -> Dict[str, Any]:
    """Add a new track to the timeline.

        Args:
        track_type: 'video', 'audio', or 'subtitle'.
        Valid: "video", "audio", "subtitle"
    sub_track_type: For audio: 'mono', 'stereo', '5.1', '7.1', 'adaptive'. Default: ''.
    new_track_options: Optional dict of track creation options.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    nto = new_track_options or {}
    if nto:
        track = tl.AddTrack(track_type, nto)
    else:
        track = tl.AddTrack(track_type, sub_track_type)
    return {"success": bool(track), "track_index": track.GetIndex() if track else None}


@mcp.tool()
def timeline_analyze_dolby_vision() -> Dict[str, Any]:
    """Analyze Dolby Vision for the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.AnalyzeDolbyVision()
    return {"success": bool(result)}


@mcp.tool()
def timeline_clear_mark_in_out() -> Dict[str, Any]:
    """Clear mark in/out points for the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.ClearMarkInOut()
    return {"success": bool(result)}


@mcp.tool()
def timeline_convert_to_stereo() -> Dict[str, Any]:
    """Convert the current timeline to stereo."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.ConvertTimelineToStereo()
    return {"success": bool(result)}


@mcp.tool()
def timeline_create_compound_clip(clip_ids: List[str], track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Create a compound clip from selected items.

        Args:
        clip_ids: List of timeline item unique IDs.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    items = tl.GetItemListInTrack(track_type, track_index)
    targets = [i for i in (items or []) if i.GetUniqueId() in clip_ids]
    if not targets:
        return {"error": "No matching items found"}
    result = tl.CreateCompoundClip(targets)
    if result:
        return {"success": True}
    return {"success": False, "error": "Failed to create compound clip"}


@mcp.tool()
def timeline_create_fusion_clip(clip_ids: List[str], track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Create a Fusion clip from selected items.

        Args:
        clip_ids: List of timeline item unique IDs.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    items = tl.GetItemListInTrack(track_type, track_index)
    targets = [i for i in (items or []) if i.GetUniqueId() in clip_ids]
    if not targets:
        return {"error": "No matching items found"}
    result = tl.CreateFusionClip(targets)
    if result:
        return {"success": True}
    return {"success": False, "error": "Failed to create Fusion clip"}


@mcp.tool()
def timeline_create_subtitles_from_audio(language: str = "auto", preset: str = "default") -> Dict[str, Any]:
    """Create subtitles from audio in the current timeline.

    Args:
    language: Language for captioning ('auto', 'english', 'french', etc.). Default: 'auto'.
    preset: Caption preset ('default', 'teletext', 'netflix'). Default: 'default'.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    settings = {}
    result = tl.CreateSubtitlesFromAudio(settings)
    return {"success": bool(result)}


@mcp.tool()
def timeline_delete_clips(clip_ids: List[str], track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Delete clips from the timeline.

        Args:
        clip_ids: List of clip unique IDs to delete.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    items = tl.GetItemListInTrack(track_type, track_index)
    if not items:
        return {"error": "No items in track"}
    to_delete = [i for i in items if i.GetUniqueId() in clip_ids]
    if not to_delete:
        return {"error": "No matching clips found"}
    result = tl.DeleteClips(to_delete)
    return {"success": bool(result), "deleted": len(to_delete)}


@mcp.tool()
def timeline_delete_marker_at_frame(frame_id: int) -> Dict[str, Any]:
    """Delete a timeline marker at a specific frame.

    Args:
    frame_id: Frame number of the marker.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.DeleteMarkerAtFrame(frame_id)
    return {"success": bool(result)}


@mcp.tool()
def timeline_delete_marker_by_custom_data(custom_data: str) -> Dict[str, Any]:
    """Delete a timeline marker by custom data.

    Args:
    custom_data: Custom data of the marker to delete.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.DeleteMarkerByCustomData(custom_data)
    return {"success": bool(result)}


@mcp.tool()
def timeline_delete_markers_by_color(color: str) -> Dict[str, Any]:
    """Delete all timeline markers of a specific color.

    Args:
    color: Color of markers to delete. Use '' to delete all.
    Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.DeleteMarkersByColor(color)
    return {"success": bool(result)}


@mcp.tool()
def timeline_delete_track(track_type: str, track_index: int) -> Dict[str, Any]:
    """Delete a track from the timeline.

        Args:
        track_type: 'video', 'audio', or 'subtitle'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index to delete.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.DeleteTrack(track_type, track_index)
    return {"success": bool(result)}


@mcp.tool()
def timeline_detect_scene_cuts() -> Dict[str, Any]:
    """Detect scene cuts in the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.DetectSceneCuts()
    return {"success": bool(result)}


@mcp.tool()
def timeline_duplicate() -> Dict[str, Any]:
    """Duplicate the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    new_tl = tl.DuplicateTimeline()
    if new_tl:
        return {
            "success": True,
            "name": new_tl.GetName(),
            "unique_id": new_tl.GetUniqueId(),
        }
    return {"success": False, "error": "Failed to duplicate timeline"}


@mcp.tool()
def timeline_export(file_path: str, export_type: str, export_subtype: str = "EXPORT_NONE") -> Dict[str, Any]:
    """Export the current timeline to a file.

    Args:
    file_path: Output file path.
    export_type: Export type (e.g. 'EXPORT_AAF', 'EXPORT_EDL', 'EXPORT_FCP_7_XML', 'EXPORT_FCPXML_1_10', 'EXPORT_DRT', 'EXPORT_TEXT_CSV', 'EXPORT_TEXT_TAB', 'EXPORT_OTIO', 'EXPORT_ALE').
    export_subtype: Export subtype for AAF/EDL. Default: 'EXPORT_NONE'.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    # Map string constants to resolve constants
    try:
        etype = getattr(resolve, export_type) if hasattr(resolve, export_type) else export_type
        esub = getattr(resolve, export_subtype) if hasattr(resolve, export_subtype) else export_subtype
    except Exception:
        etype = export_type
        esub = export_subtype
    result = tl.Export(file_path, etype, esub)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def timeline_get_current_clip_thumbnail(width: int = 320, height: int = 180) -> Dict[str, Any]:
    """Get thumbnail image data for the current clip.

    Args:
    width: Thumbnail width. Default: 320.
    height: Thumbnail height. Default: 180.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.GetCurrentClipThumbnailImage()
    if result:
        return {"success": True, "has_data": bool(result)}
    return {"success": False}


@mcp.tool()
def timeline_get_current_timecode() -> Dict[str, Any]:
    """Get the current playhead timecode."""
    _, tl, err = _get_timeline()
    if err:
        return err
    return {"timecode": tl.GetCurrentTimecode()}


@mcp.tool()
def timeline_get_is_track_enabled(track_type: str, track_index: int) -> Dict[str, Any]:
    """Check if a track is enabled.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    enabled = tl.GetIsTrackEnabled(track_type, track_index)
    return {"enabled": bool(enabled)}


@mcp.tool()
def timeline_get_is_track_locked(track_type: str, track_index: int) -> Dict[str, Any]:
    """Check if a track is locked.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    locked = tl.GetIsTrackLocked(track_type, track_index)
    return {"locked": bool(locked)}


@mcp.tool()
def timeline_get_mark_in_out() -> Dict[str, Any]:
    """Get mark in/out points for the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.GetMarkInOut()
    return result if result else {}


@mcp.tool()
def timeline_get_marker_by_custom_data(custom_data: str) -> Dict[str, Any]:
    """Find a timeline marker by its custom data.

    Args:
    custom_data: Custom data string to search for.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    marker = tl.GetMarkerByCustomData(custom_data)
    return {"marker": marker if marker else {}}


@mcp.tool()
def timeline_get_marker_custom_data(frame_id: int) -> Dict[str, Any]:
    """Get the custom data of a timeline marker.

    Args:
    frame_id: Frame number of the marker.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    data = tl.GetMarkerCustomData(frame_id)
    return {"frame_id": frame_id, "custom_data": data if data else ""}


@mcp.tool()
def timeline_get_markers() -> Dict[str, Any]:
    """Get all markers on the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    markers = tl.GetMarkers()
    return {"markers": markers if markers else {}}


@mcp.tool()
def timeline_get_media_pool_item() -> Dict[str, Any]:
    """Get the MediaPoolItem for the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    mpi = tl.GetMediaPoolItem()
    if mpi:
        return {"name": mpi.GetName(), "unique_id": mpi.GetUniqueId()}
    return {"media_pool_item": None}


@mcp.tool()
def timeline_get_node_graph() -> Dict[str, Any]:
    """Get the node graph for the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    graph = tl.GetNodeGraph()
    if graph:
        return {"has_graph": True, "num_nodes": graph.GetNumNodes()}
    return {"has_graph": False}


@mcp.tool()
def timeline_get_track_name(track_type: str, track_index: int) -> Dict[str, Any]:
    """Get the name of a track.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    name = tl.GetTrackName(track_type, track_index)
    return {"track_name": name if name else ""}


@mcp.tool()
def timeline_get_track_sub_type(track_type: str, track_index: int) -> Dict[str, Any]:
    """Get the sub-type of a track (e.g. mono, stereo for audio).

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    sub = tl.GetTrackSubType(track_type, track_index)
    return {
        "track_type": track_type,
        "track_index": track_index,
        "sub_type": sub if sub else "",
    }


@mcp.tool()
def timeline_get_unique_id() -> Dict[str, Any]:
    """Get the unique ID of the current timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    return {"unique_id": tl.GetUniqueId()}


@mcp.tool()
def timeline_grab_all_stills() -> Dict[str, Any]:
    """Grab stills from all frames at the current position across all timelines."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.GrabAllStills()
    return {"success": result is not None}


@mcp.tool()
def timeline_grab_still() -> Dict[str, Any]:
    """Grab a still from the current frame of the timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.GrabStill()
    return {"success": result is not None}


@mcp.tool()
def timeline_import_into(file_path: str, import_options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Import content into the current timeline from a file.

    Args:
    file_path: Path to the file to import (AAF, EDL, XML, etc.).
    import_options: Optional dict of import options.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    if import_options:
        result = tl.ImportIntoTimeline(file_path, import_options)
    else:
        result = tl.ImportIntoTimeline(file_path)
    return {"success": bool(result)}


@mcp.tool()
def timeline_insert_fusion_composition() -> Dict[str, Any]:
    """Insert a Fusion composition into the timeline."""
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.InsertFusionCompositionIntoTimeline()
    return {"success": result is not None}


@mcp.tool()
def timeline_insert_fusion_generator(generator_name: str) -> Dict[str, Any]:
    """Insert a Fusion generator into the timeline.

    Args:
    generator_name: Name of the Fusion generator.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.InsertFusionGeneratorIntoTimeline(generator_name)
    return {"success": result is not None}


@mcp.tool()
def timeline_insert_fusion_title(title_name: str) -> Dict[str, Any]:
    """Insert a Fusion title into the timeline.

    Args:
    title_name: Name of the Fusion title.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.InsertFusionTitleIntoTimeline(title_name)
    return {"success": result is not None}


@mcp.tool()
def timeline_insert_generator(generator_name: str, duration: Optional[int] = None) -> Dict[str, Any]:
    """Insert a generator into the timeline.

    Args:
    generator_name: Name of the generator to insert.
    duration: Optional duration in frames.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    if duration:
        result = tl.InsertGeneratorIntoTimeline(generator_name, {"duration": duration})
    else:
        result = tl.InsertGeneratorIntoTimeline(generator_name)
    return {"success": result is not None}


@mcp.tool()
def timeline_insert_ofx_generator(generator_name: str) -> Dict[str, Any]:
    """Insert an OFX generator into the timeline.

    Args:
    generator_name: Name of the OFX generator.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.InsertOFXGeneratorIntoTimeline(generator_name)
    return {"success": result is not None}


@mcp.tool()
def timeline_insert_title(title_name: str) -> Dict[str, Any]:
    """Insert a title into the timeline.

    Args:
    title_name: Name of the title to insert.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.InsertTitleIntoTimeline(title_name)
    return {"success": result is not None}


@mcp.tool()
def timeline_set_clips_linked(clip_ids: List[str], linked: bool, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Link or unlink clips in the timeline.

        Args:
        clip_ids: List of clip unique IDs.
    linked: True to link, False to unlink.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    items = tl.GetItemListInTrack(track_type, track_index)
    if not items:
        return {"error": "No items in track"}
    targets = [i for i in items if i.GetUniqueId() in clip_ids]
    if not targets:
        return {"error": "No matching clips found"}
    result = tl.SetClipsLinked(targets, linked)
    return {"success": bool(result)}


@mcp.tool()
def timeline_set_current_timecode(timecode: str) -> Dict[str, Any]:
    """Set the playhead to a specific timecode.

    Args:
    timecode: Timecode string (e.g. '01:00:05:00').
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetCurrentTimecode(timecode)
    return {"success": bool(result), "timecode": timecode}


@mcp.tool()
def timeline_set_mark_in_out(mark_in: int, mark_out: int) -> Dict[str, Any]:
    """Set mark in/out points for the current timeline.

    Args:
    mark_in: Mark in frame number.
    mark_out: Mark out frame number.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetMarkInOut(mark_in, mark_out)
    return {"success": bool(result)}


@mcp.tool()
def timeline_set_name(name: str) -> Dict[str, Any]:
    """Rename the current timeline.

    Args:
    name: New name for the timeline.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetName(name)
    return {"success": bool(result), "name": name}


@mcp.tool()
def timeline_set_start_timecode(timecode: str) -> Dict[str, Any]:
    """Set the start timecode of the current timeline.

    Args:
    timecode: Timecode string (e.g. '01:00:00:00').
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetStartTimecode(timecode)
    return {"success": bool(result), "timecode": timecode}


@mcp.tool()
def timeline_set_track_enable(track_type: str, track_index: int, enabled: bool) -> Dict[str, Any]:
    """Enable or disable a track.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    enabled: True to enable, False to disable.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetTrackEnable(track_type, track_index, enabled)
    return {"success": bool(result)}


@mcp.tool()
def timeline_set_track_lock(track_type: str, track_index: int, locked: bool) -> Dict[str, Any]:
    """Lock or unlock a track.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    locked: True to lock, False to unlock.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetTrackLock(track_type, track_index, locked)
    return {"success": bool(result)}


@mcp.tool()
def timeline_set_track_name(track_type: str, track_index: int, name: str) -> Dict[str, Any]:
    """Set the name of a track.

        Args:
        track_type: 'video' or 'audio'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index.
    name: New track name.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.SetTrackName(track_type, track_index, name)
    return {"success": bool(result)}


@mcp.tool()
def timeline_update_marker_custom_data(frame_id: int, custom_data: str) -> Dict[str, Any]:
    """Update the custom data of a timeline marker.

    Args:
    frame_id: Frame number of the marker.
    custom_data: New custom data string.
    """
    _, tl, err = _get_timeline()
    if err:
        return err
    result = tl.UpdateMarkerCustomData(frame_id, custom_data)
    return {"success": bool(result)}
