#!/usr/bin/env python3
"""Granular server — media_pool_item tools."""

# ── Shared mcp server (defined in granular/__init__.py) ───────────
# ── Imports ──────────────────────────────────────────────────────
import logging
import os
import platform
import subprocess
import tempfile
import time
from typing import Any, Dict, List

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
    if isinstance(value, (list, tuple)):
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


def get_current_page() -> Dict[str, Any]:
    """Get the current page open in DaVinci Resolve (Edit, Color, Fusion, etc.)."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    return {"page": resolve.GetCurrentPage()}


def get_current_project():
    """Get current project with lazy connection and null guards."""
    pm = get_project_manager()
    if not pm:
        return None, None
    proj = pm.GetCurrentProject()
    return pm, proj


def get_current_project_name() -> Dict[str, Any]:
    """Get the name of the currently open project."""
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    return {"project_name": current_project.GetName()}


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


def get_resolve_version() -> Dict[str, Any]:
    """Get DaVinci Resolve version information."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    return {
        "product": resolve.GetProductName(),
        "version": resolve.GetVersion(),
        "version_string": resolve.GetVersionString(),
    }


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
def add_clip_flag(clip_id: str, color: str) -> Dict[str, Any]:
    """Add a flag to a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    color: Flag color (Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream).
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.AddFlag(color)
    return {"success": bool(result)}


@mcp.tool()
def add_clip_marker(
    clip_id: str,
    frame_id: int,
    color: str,
    name: str,
    note: str = "",
    duration: int = 1,
    custom_data: str = "",
) -> Dict[str, Any]:
    """Add a marker to a Media Pool clip.

        Args:
        clip_id: Unique ID of the clip.
    frame_id: Frame number for the marker.
    color: Marker color (Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, Sky, Mint, Lemon, Sand, Cocoa, Cream).
        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    name: Marker name.
    note: Marker note. Default: empty.
    duration: Marker duration in frames. Default: 1.
    custom_data: Custom data string. Default: empty.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.AddMarker(frame_id, color, name, note, duration, custom_data)
    return {"success": bool(result)}


@mcp.tool()
def clear_clip_color(clip_id: str) -> Dict[str, Any]:
    """Clear the clip color of a Media Pool item.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.ClearClipColor()
    return {"success": bool(result)}


@mcp.tool()
def clear_clip_flags(clip_id: str, color: str = "") -> Dict[str, Any]:
    """Clear flags on a clip.

    Args:
    clip_id: Unique ID of the clip.
    color: Specific color to clear, or empty for all colors.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.ClearFlags(color)
    return {"success": bool(result)}


@mcp.tool()
def clear_clip_mark_in_out(clip_id: str) -> Dict[str, Any]:
    """Clear mark in/out points for a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.ClearMarkInOut()
    return {"success": bool(result)}


@mcp.tool()
def clear_clip_transcription(clip_id: str) -> Dict[str, Any]:
    """Clear transcription for a specific clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.ClearTranscription()
    return {"success": bool(result)}


@mcp.tool()
def clear_transcription(clip_name: str) -> str:
    """Clear audio transcription for a clip.

    Args:
    clip_name: Name of the clip to clear transcription from
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find the clip by name
    clips = get_all_media_pool_clips(media_pool)
    target_clip = None

    for clip in clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break

    if not target_clip:
        return f"Error: Clip '{clip_name}' not found in Media Pool"

    try:
        result = target_clip.ClearTranscription()
        if result:
            return f"Successfully cleared audio transcription for clip '{clip_name}'"
        else:
            return f"Failed to clear audio transcription for clip '{clip_name}'"
    except Exception as e:
        return f"Error clearing audio transcription: {str(e)}"


@mcp.tool()
def create_stereo_clip(left_clip_id: str, right_clip_id: str) -> Dict[str, Any]:
    """Create a stereo clip from left and right eye clips.

    Args:
    left_clip_id: Unique ID of the left eye clip.
    right_clip_id: Unique ID of the right eye clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    root = mp.GetRootFolder()
    left = _find_clip_by_id(root, left_clip_id)
    right = _find_clip_by_id(root, right_clip_id)
    if not left:
        return {"error": f"Left clip {left_clip_id} not found"}
    if not right:
        return {"error": f"Right clip {right_clip_id} not found"}
    result = mp.CreateStereoClip(left, right)
    return {"success": bool(result)}


@mcp.tool()
def create_sub_clip(
    clip_name: str,
    start_frame: int,
    end_frame: int,
    sub_clip_name: str = None,
    bin_name: str = None,
) -> str:
    """Create a subclip from the specified clip using in and out points.

    Args:
    clip_name: Name of the source clip
    start_frame: Start frame (in point)
    end_frame: End frame (out point)
    sub_clip_name: Optional name for the subclip (defaults to original name with '_subclip')
    bin_name: Optional bin to place the subclip in
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def delete_clip_marker_at_frame(clip_id: str, frame_id: int) -> Dict[str, Any]:
    """Delete a marker at a specific frame on a clip.

    Args:
    clip_id: Unique ID of the clip.
    frame_id: Frame number of the marker to delete.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.DeleteMarkerAtFrame(frame_id)
    return {"success": bool(result)}


@mcp.tool()
def delete_clip_marker_by_custom_data(clip_id: str, custom_data: str) -> Dict[str, Any]:
    """Delete a marker by its custom data string.

    Args:
    clip_id: Unique ID of the clip.
    custom_data: Custom data string of the marker to delete.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.DeleteMarkerByCustomData(custom_data)
    return {"success": bool(result)}


@mcp.tool()
def delete_clip_markers_by_color(clip_id: str, color: str) -> Dict[str, Any]:
    """Delete all markers of a specific color on a clip.

        Args:
        clip_id: Unique ID of the clip.
    color: Color of markers to delete. Use '' to delete all.
        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.DeleteMarkersByColor(color)
    return {"success": bool(result)}


@mcp.tool()
def delete_optimized_media(clip_names: List[str] = None) -> str:
    """Delete optimized media for specified clips or all clips if none specified.

    Args:
    clip_names: Optional list of clip names. If None, processes all clips in media pool
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Get clips to process
    if clip_names:
        # Get specified clips
        all_clips = get_all_media_pool_clips(media_pool)
        clips_to_process = []
        missing_clips = []

        for name in clip_names:
            found = False
            for clip in all_clips:
                if clip.GetName() == name:
                    clips_to_process.append(clip)
                    found = True
                    break
            if not found:
                missing_clips.append(name)

        if missing_clips:
            return f"Error: Could not find these clips: {', '.join(missing_clips)}"

        if not clips_to_process:
            return "Error: No valid clips found to process"
    else:
        # Get all clips
        clips_to_process = get_all_media_pool_clips(media_pool)

    try:
        # Select the clips
        media_pool.SetCurrentFolder(media_pool.GetRootFolder())
        for clip in clips_to_process:
            clip.AddFlag("Green")  # Temporarily add flag to help with selection

        # Switch to Media page if not already there
        current_page = resolve.GetCurrentPage()
        if current_page != "media":
            resolve.OpenPage("media")

        # Select clips with Green flag
        media_pool.SetClipSelection([clip for clip in clips_to_process])

        # Delete optimized media
        result = current_project.DeleteOptimizedMedia()

        # Remove temporary flags
        for clip in clips_to_process:
            clip.ClearFlags("Green")

        if result:
            return f"Successfully deleted optimized media for {len(clips_to_process)} clips"
        else:
            return "Failed to delete optimized media"
    except Exception as e:
        # Clean up flags in case of error
        try:
            for clip in clips_to_process:
                clip.ClearFlags("Green")
        except Exception:
            pass
        return f"Error deleting optimized media: {str(e)}"


@mcp.tool()
def generate_optimized_media(clip_names: List[str] = None) -> str:
    """Generate optimized media for specified clips or all clips if none specified.

    Args:
    clip_names: Optional list of clip names. If None, processes all clips in media pool
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Get clips to process
    if clip_names:
        # Get specified clips
        all_clips = get_all_media_pool_clips(media_pool)
        clips_to_process = []
        missing_clips = []

        for name in clip_names:
            found = False
            for clip in all_clips:
                if clip.GetName() == name:
                    clips_to_process.append(clip)
                    found = True
                    break
            if not found:
                missing_clips.append(name)

        if missing_clips:
            return f"Error: Could not find these clips: {', '.join(missing_clips)}"

        if not clips_to_process:
            return "Error: No valid clips found to process"
    else:
        # Get all clips
        clips_to_process = get_all_media_pool_clips(media_pool)

    try:
        # Select the clips
        media_pool.SetCurrentFolder(media_pool.GetRootFolder())
        for clip in clips_to_process:
            clip.AddFlag("Green")  # Temporarily add flag to help with selection

        # Switch to Media page if not already there
        current_page = resolve.GetCurrentPage()
        if current_page != "media":
            resolve.OpenPage("media")

        # Select clips with Green flag
        media_pool.SetClipSelection([clip for clip in clips_to_process])

        # Generate optimized media
        result = current_project.GenerateOptimizedMedia()

        # Remove temporary flags
        for clip in clips_to_process:
            clip.ClearFlags("Green")

        if result:
            return f"Successfully started optimized media generation for {len(clips_to_process)} clips"
        else:
            return "Failed to start optimized media generation"
    except Exception as e:
        # Clean up flags in case of error
        try:
            for clip in clips_to_process:
                clip.ClearFlags("Green")
        except Exception:
            pass
        return f"Error generating optimized media: {str(e)}"


@mcp.tool()
def get_clip_audio_mapping(clip_id: str) -> Dict[str, Any]:
    """Get audio mapping for a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    mapping = clip.GetAudioMapping()
    return {"clip_id": clip_id, "audio_mapping": mapping if mapping else ""}


@mcp.tool()
def get_clip_color(clip_id: str) -> Dict[str, Any]:
    """Get the clip color of a Media Pool item.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    color = clip.GetClipColor()
    return {"clip_id": clip_id, "clip_color": color if color else ""}


@mcp.tool()
def get_clip_flag_list(clip_id: str) -> Dict[str, Any]:
    """Get list of flags on a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    flags = clip.GetFlagList()
    return {"clip_id": clip_id, "flags": flags if flags else []}


@mcp.tool()
def get_clip_mark_in_out(clip_id: str) -> Dict[str, Any]:
    """Get mark in/out points for a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.GetMarkInOut()
    return {"clip_id": clip_id, "mark_in_out": result if result else {}}


@mcp.tool()
def get_clip_marker_by_custom_data(clip_id: str, custom_data: str) -> Dict[str, Any]:
    """Get a marker by its custom data string.

    Args:
    clip_id: Unique ID of the clip.
    custom_data: Custom data string to search for.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    marker = clip.GetMarkerByCustomData(custom_data)
    return {"marker": marker if marker else {}}


@mcp.tool()
def get_clip_marker_custom_data(clip_id: str, frame_id: int) -> Dict[str, Any]:
    """Get the custom data of a clip marker at a specific frame.

    Args:
    clip_id: Unique ID of the clip.
    frame_id: Frame number of the marker.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    data = clip.GetMarkerCustomData(frame_id)
    return {"frame_id": frame_id, "custom_data": data if data else ""}


@mcp.tool()
def get_clip_markers(clip_id: str) -> Dict[str, Any]:
    """Get all markers on a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    markers = clip.GetMarkers()
    return {"clip_id": clip_id, "markers": markers if markers else {}}


@mcp.tool()
def get_clip_media_id(clip_id: str) -> Dict[str, Any]:
    """Get the media ID for a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    media_id = clip.GetMediaId()
    return {"clip_id": clip_id, "media_id": media_id}


@mcp.tool()
def get_clip_metadata(clip_id: str, metadata_type: str = "") -> Dict[str, Any]:
    """Get metadata for a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    metadata_type: Specific metadata key, or empty for all metadata.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    if metadata_type:
        result = clip.GetMetadata(metadata_type)
    else:
        result = clip.GetMetadata()
    return {"clip_id": clip_id, "metadata": result if result else {}}


@mcp.tool()
def get_clip_property(clip_id: str, property_name: str = "") -> Dict[str, Any]:
    """Get a property of a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    property_name: Property name, or empty for all properties.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    if property_name:
        result = clip.GetClipProperty(property_name)
    else:
        result = clip.GetClipProperty()
    return {"clip_id": clip_id, "property": result if result else {}}


@mcp.tool()
def get_clip_third_party_metadata(clip_id: str, metadata_key: str = "") -> Dict[str, Any]:
    """Get third-party metadata for a clip.

    Args:
    clip_id: Unique ID of the clip.
    metadata_key: Specific key, or empty for all.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    if metadata_key:
        result = clip.GetThirdPartyMetadata(metadata_key)
    else:
        result = clip.GetThirdPartyMetadata()
    return {"clip_id": clip_id, "third_party_metadata": result if result else {}}


@mcp.tool()
def get_clip_unique_id_by_name(clip_name: str) -> Dict[str, Any]:
    """Find a clip by name and return its unique ID.

    Args:
    clip_name: Name of the clip to find.
    """
    _, mp, err = _get_mp()
    if err:
        return err

    def search(folder):
        for clip in folder.GetClipList() or []:
            if clip.GetName() == clip_name:
                return clip
        for sub in folder.GetSubFolderList() or []:
            found = search(sub)
            if found:
                return found
        return None

    clip = search(mp.GetRootFolder())
    if clip:
        return {"name": clip.GetName(), "unique_id": clip.GetUniqueId()}
    return {"error": f"Clip '{clip_name}' not found"}


@mcp.tool()
def get_selected_clips() -> Dict[str, Any]:
    """Get currently selected clips in the Media Pool."""
    _, mp, err = _get_mp()
    if err:
        return err
    clips = mp.GetSelectedClips()
    if clips:
        result = []
        for clip in clips:
            try:
                result.append({"name": clip.GetName(), "unique_id": clip.GetUniqueId()})
            except Exception:
                result.append({"name": "Unknown"})
        return {"selected_clips": result}
    return {"selected_clips": []}


@mcp.tool()
def link_clip_proxy_media(clip_id: str, proxy_path: str) -> Dict[str, Any]:
    """Link proxy media to a clip.

    Args:
    clip_id: Unique ID of the clip.
    proxy_path: Absolute path to the proxy media file.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.LinkProxyMedia(proxy_path)
    return {"success": bool(result)}


@mcp.tool()
def link_full_resolution_media(clip_id: str) -> str:
    """Link full resolution media to a media pool clip.

    Args:
    clip_id: The unique ID of the clip to link full resolution media to
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find clip by ID
    root_folder = media_pool.GetRootFolder()
    clip = _find_clip_by_id(root_folder, clip_id)
    if not clip:
        return f"Error: Clip with ID '{clip_id}' not found"

    try:
        result = clip.LinkFullResolutionMedia()
        if result:
            return f"Successfully linked full resolution media to clip '{clip_id}'"
        else:
            return "Failed to link full resolution media"
    except Exception as e:
        return f"Error linking full resolution media: {str(e)}"


@mcp.tool()
def monitor_growing_file(clip_id: str) -> str:
    """Monitor a growing file for a media pool clip.

    Args:
    clip_id: The unique ID of the clip to monitor
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find clip by ID
    root_folder = media_pool.GetRootFolder()
    clip = _find_clip_by_id(root_folder, clip_id)
    if not clip:
        return f"Error: Clip with ID '{clip_id}' not found"

    try:
        result = clip.MonitorGrowingFile()
        if result:
            return f"Successfully started monitoring growing file for clip '{clip_id}'"
        else:
            return "Failed to start monitoring growing file"
    except Exception as e:
        return f"Error monitoring growing file: {str(e)}"


@mcp.tool()
def relink_clips(
    clip_names: List[str],
    media_paths: List[str] = None,
    folder_path: str = None,
    recursive: bool = False,
) -> str:
    """Relink specified clips to their media files.

    Args:
    clip_names: List of clip names to relink
    media_paths: Optional list of specific media file paths to use for relinking
    folder_path: Optional folder path to search for media files
    recursive: Whether to search the folder path recursively
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def replace_clip(clip_name: str, replacement_path: str) -> str:
    """Replace a clip with another media file.

    Args:
    clip_name: Name of the clip to be replaced
    replacement_path: Path to the replacement media file
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find the clip by name
    clips = get_all_media_pool_clips(media_pool)
    target_clip = None

    for clip in clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break

    if not target_clip:
        return f"Error: Clip '{clip_name}' not found in Media Pool"

    # Check if file exists
    if not os.path.exists(replacement_path):
        return f"Error: Replacement file '{replacement_path}' does not exist"

    try:
        result = target_clip.ReplaceClip(replacement_path)
        if result:
            return f"Successfully replaced clip '{clip_name}' with '{replacement_path}'"
        else:
            return f"Failed to replace clip '{clip_name}'"
    except Exception as e:
        return f"Error replacing clip: {str(e)}"


@mcp.tool()
def replace_media_pool_clip(clip_id: str, new_file_path: str) -> Dict[str, Any]:
    """Replace a clip with a new media file.

    Args:
    clip_id: Unique ID of the clip to replace.
    new_file_path: Absolute path to the new media file.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.ReplaceClip(new_file_path)
    return {"success": bool(result)}


@mcp.tool()
def set_clip_color(clip_id: str, color: str) -> Dict[str, Any]:
    """Set the clip color of a Media Pool item.

    Args:
    clip_id: Unique ID of the clip.
    color: Color name (Orange, Apricot, Yellow, Lime, Olive, Green, Teal, Navy, Blue, Purple, Violet, Pink, Tan, Beige, Brown, Chocolate).
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.SetClipColor(color)
    return {"success": bool(result)}


@mcp.tool()
def set_clip_mark_in_out(clip_id: str, mark_in: int, mark_out: int) -> Dict[str, Any]:
    """Set mark in/out points for a clip.

    Args:
    clip_id: Unique ID of the clip.
    mark_in: Mark in frame number.
    mark_out: Mark out frame number.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.SetMarkInOut(mark_in, mark_out)
    return {"success": bool(result)}


@mcp.tool()
def set_clip_metadata(clip_id: str, metadata: Dict[str, str]) -> Dict[str, Any]:
    """Set metadata on a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    metadata: Dict of metadata key-value pairs to set.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.SetMetadata(metadata)
    return {"success": bool(result)}


@mcp.tool()
def set_clip_property(clip_id: str, property_name: str, property_value: str) -> Dict[str, Any]:
    """Set a property on a Media Pool clip.

    Args:
    clip_id: Unique ID of the clip.
    property_name: Property name (e.g. 'Clip Name', 'Comments', 'Description').
    property_value: Value to set.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.SetClipProperty(property_name, property_value)
    return {"success": bool(result)}


@mcp.tool()
def set_clip_third_party_metadata(clip_id: str, metadata: Dict[str, str]) -> Dict[str, Any]:
    """Set third-party metadata on a clip.

    Args:
    clip_id: Unique ID of the clip.
    metadata: Dict of metadata key-value pairs.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.SetThirdPartyMetadata(metadata)
    return {"success": bool(result)}


@mcp.tool()
def set_media_pool_item_name(clip_id: str, name: str) -> str:
    """Set the name of a media pool clip.

    Args:
    clip_id: The unique ID of the clip to rename
    name: The new name for the clip
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find clip by ID
    root_folder = media_pool.GetRootFolder()
    clip = _find_clip_by_id(root_folder, clip_id)
    if not clip:
        return f"Error: Clip with ID '{clip_id}' not found"

    try:
        result = clip.SetName(name)
        if result:
            return f"Successfully renamed clip to '{name}'"
        else:
            return "Failed to rename clip"
    except Exception as e:
        return f"Error renaming clip: {str(e)}"


@mcp.tool()
def transcribe_audio(clip_name: str, language: str = "en-US") -> str:
    """Transcribe audio for a clip.

    Args:
    clip_name: Name of the clip to transcribe
    language: Language code for transcription (default: en-US)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find the clip by name
    clips = get_all_media_pool_clips(media_pool)
    target_clip = None

    for clip in clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break

    if not target_clip:
        return f"Error: Clip '{clip_name}' not found in Media Pool"

    try:
        result = target_clip.TranscribeAudio(language)
        if result:
            return f"Successfully started audio transcription for clip '{clip_name}' in language '{language}'"
        else:
            return f"Failed to start audio transcription for clip '{clip_name}'"
    except Exception as e:
        return f"Error during audio transcription: {str(e)}"


@mcp.tool()
def transcribe_clip_audio(clip_id: str) -> Dict[str, Any]:
    """Transcribe audio for a specific clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.TranscribeAudio()
    return {"success": bool(result)}


@mcp.tool()
def unlink_clip_proxy_media(clip_id: str) -> Dict[str, Any]:
    """Unlink proxy media from a clip.

    Args:
    clip_id: Unique ID of the clip.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.UnlinkProxyMedia()
    return {"success": bool(result)}


@mcp.tool()
def unlink_clips(clip_names: List[str]) -> str:
    """Unlink specified clips, disconnecting them from their media files.

    Args:
    clip_names: List of clip names to unlink
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def unlink_proxy_media(clip_name: str) -> str:
    """Unlink proxy media from a clip.

    Args:
    clip_name: Name of the clip to unlink proxy from
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    # Find the clip by name
    clips = get_all_media_pool_clips(media_pool)
    target_clip = None

    for clip in clips:
        if clip.GetName() == clip_name:
            target_clip = clip
            break

    if not target_clip:
        return f"Error: Clip '{clip_name}' not found in Media Pool"

    try:
        result = target_clip.UnlinkProxyMedia()
        if result:
            return f"Successfully unlinked proxy media from clip '{clip_name}'"
        else:
            return f"Failed to unlink proxy media from clip '{clip_name}'"
    except Exception as e:
        return f"Error unlinking proxy media: {str(e)}"


@mcp.tool()
def update_clip_marker_custom_data(clip_id: str, frame_id: int, custom_data: str) -> Dict[str, Any]:
    """Update the custom data of a clip marker.

    Args:
    clip_id: Unique ID of the clip.
    frame_id: Frame number of the marker.
    custom_data: New custom data string.
    """
    _, mp, err = _get_mp()
    if err:
        return err
    clip = _find_clip_by_id(mp.GetRootFolder(), clip_id)
    if not clip:
        return {"error": f"Clip {clip_id} not found"}
    result = clip.UpdateMarkerCustomData(frame_id, custom_data)
    return {"success": bool(result)}
