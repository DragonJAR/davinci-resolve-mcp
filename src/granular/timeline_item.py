#!/usr/bin/env python3
"""Granular server — timeline_item tools."""

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
def add_keyframe(timeline_item_id: str, property_name: str, frame: int, value: float) -> str:
    """Add a keyframe at the specified frame for a timeline item property.

    Args:
    timeline_item_id: The ID of the timeline item to add keyframe to
    property_name: The name of the property to keyframe (e.g., 'Pan', 'ZoomX')
    frame: Frame position for the keyframe
    value: Value to set at the keyframe
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Valid keyframeable properties
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

    audio_properties = ["Volume", "Pan"]

    valid_properties = video_properties + audio_properties

    if property_name not in valid_properties:
        return f"Error: Invalid property name. Must be one of: {', '.join(valid_properties)}"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")
        audio_track_count = current_timeline.GetTrackCount("audio")

        timeline_item = None
        is_audio = False

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
                            is_audio = True
                            break
                if timeline_item:
                    break

        if not timeline_item:
            return f"Error: Timeline item with ID '{timeline_item_id}' not found"

        # Check if the specified property is valid for this item type
        if is_audio and property_name not in audio_properties:
            return f"Error: Property '{property_name}' is not available for audio items"

        if not is_audio and property_name not in video_properties and timeline_item.GetType() != "Video":
            return f"Error: Property '{property_name}' is not available for this item type"

        # Validate frame is within the item's range
        start_frame = timeline_item.GetStart()
        end_frame = timeline_item.GetEnd()

        if frame < start_frame or frame > end_frame:
            return f"Error: Frame {frame} is outside the item's range ({start_frame} to {end_frame})"

        # Add the keyframe
        result = timeline_item.AddKeyframe(property_name, frame, value)

        if result:
            return f"Successfully added keyframe for {property_name} at frame {frame} with value {value}"
        else:
            return f"Failed to add keyframe for {property_name} at frame {frame}"

    except Exception as e:
        return f"Error adding keyframe: {str(e)}"


@mcp.tool()
def delete_keyframe(timeline_item_id: str, property_name: str, frame: int) -> str:
    """Delete a keyframe at the specified frame for a timeline item property.

    Args:
    timeline_item_id: The ID of the timeline item
    property_name: The name of the property with keyframe to delete
    frame: Frame position of the keyframe to delete
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

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
            return f"Error: Timeline item with ID '{timeline_item_id}' not found"

        # Check if the property has keyframes
        keyframe_count = timeline_item.GetKeyframeCount(property_name)
        if keyframe_count == 0:
            return f"Error: No keyframes found for property '{property_name}'"

        # Check if there's a keyframe at the specified frame
        keyframe_exists = False
        for i in range(keyframe_count):
            kf = timeline_item.GetKeyframeAtIndex(property_name, i)
            if kf["frame"] == frame:
                keyframe_exists = True
                break

        if not keyframe_exists:
            return f"Error: No keyframe found at frame {frame} for property '{property_name}'"

        # Delete the keyframe
        result = timeline_item.DeleteKeyframe(property_name, frame)

        if result:
            return f"Successfully deleted keyframe for {property_name} at frame {frame}"
        else:
            return f"Failed to delete keyframe for {property_name} at frame {frame}"

    except Exception as e:
        return f"Error deleting keyframe: {str(e)}"


@mcp.tool()
def enable_keyframes(timeline_item_id: str, keyframe_mode: str = "All") -> str:
    """Enable keyframe mode for a timeline item.

        Args:
        timeline_item_id: The ID of the timeline item
    keyframe_mode: Keyframe mode to enable. Options: 'All', 'Color', 'Sizing'
        Valid: 0=Linear, 1=Bezier, 2=Constant
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate keyframe mode
    valid_keyframe_modes = ["All", "Color", "Sizing"]
    if keyframe_mode not in valid_keyframe_modes:
        return f"Error: Invalid keyframe mode. Must be one of: {', '.join(valid_keyframe_modes)}"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        if timeline_item.GetType() != "Video":
            return f"Error: Timeline item with ID '{timeline_item_id}' is not a video item"

        # Set the keyframe mode
        keyframe_mode_map = {"All": 0, "Color": 1, "Sizing": 2}

        result = timeline_item.SetProperty("KeyframeMode", keyframe_mode_map[keyframe_mode])

        if result:
            return f"Successfully enabled {keyframe_mode} keyframe mode for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to enable {keyframe_mode} keyframe mode for timeline item '{timeline_item.GetName()}'"

    except Exception as e:
        return f"Error enabling keyframe mode: {str(e)}"


@mcp.tool()
def get_fusion_comp_by_name(comp_name: str, track_type: str = "video", track_index: int = 1, item_index: int = 0) -> Dict[str, Any]:
    """Get a Fusion composition from a timeline item by name.

        Args:
        comp_name: Name of the Fusion composition to retrieve.
    track_type: Track type ('video', 'audio', 'subtitle').
        Valid: "video", "audio", "subtitle"
    track_index: Track index (1-based).
    item_index: Item index on the track (0-based).
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    comp = item.GetFusionCompByName(comp_name)
    if comp:
        return {"success": True, "comp_name": comp_name, "comp_available": True}
    return {
        "success": False,
        "error": f"Fusion composition '{comp_name}' not found on this timeline item",
    }


@mcp.tool()
def graph_get_node_cache_mode(
    node_index: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get the cache mode of a node.

        Args:
        node_index: 1-based node index.
    item_index: 0-based timeline item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    mode = graph.GetNodeCacheMode(node_index)
    modes = {-1: "Auto", 0: "Disabled", 1: "Enabled"}
    return {
        "node_index": node_index,
        "cache_mode": mode,
        "mode_name": modes.get(mode, "Unknown"),
    }


@mcp.tool()
def graph_get_node_label(
    node_index: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get the label of a node.

        Args:
        node_index: 1-based node index.
    item_index: 0-based timeline item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    label = graph.GetNodeLabel(node_index)
    return {"node_index": node_index, "label": label if label else ""}


@mcp.tool()
def graph_get_num_nodes(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get number of nodes in the color graph for a timeline item.

        Args:
        item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    return {"num_nodes": graph.GetNumNodes()}


@mcp.tool()
def graph_get_tools_in_node(
    node_index: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get list of tools used in a node.

        Args:
        node_index: 1-based node index.
    item_index: 0-based timeline item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    tools = graph.GetToolsInNode(node_index)
    return {"node_index": node_index, "tools": tools if tools else []}


@mcp.tool()
def graph_set_node_cache_mode(
    node_index: int,
    cache_value: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Set the cache mode on a node.

        Args:
        node_index: 1-based node index.
    cache_value: -1=Auto, 0=Disabled, 1=Enabled.
    item_index: 0-based timeline item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    result = graph.SetNodeCacheMode(node_index, cache_value)
    return {"success": bool(result)}


@mcp.tool()
def graph_set_node_enabled(
    node_index: int,
    is_enabled: bool,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Enable or disable a node.

        Args:
        node_index: 1-based node index.
    is_enabled: True to enable, False to disable.
    item_index: 0-based timeline item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if not graph:
        return {"error": "No node graph available"}
    result = graph.SetNodeEnabled(node_index, is_enabled)
    return {"success": bool(result)}


@mcp.tool()
def modify_keyframe(
    timeline_item_id: str,
    property_name: str,
    frame: int,
    new_value: float = None,
    new_frame: int = None,
) -> str:
    """Modify an existing keyframe by changing its value or frame position.

    Args:
    timeline_item_id: The ID of the timeline item
    property_name: The name of the property with keyframe
    frame: Current frame position of the keyframe to modify
    new_value: Optional new value for the keyframe
    new_frame: Optional new frame position for the keyframe
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    if new_value is None and new_frame is None:
        return "Error: Must specify at least one of new_value or new_frame"

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
            return f"Error: Timeline item with ID '{timeline_item_id}' not found"

        # Check if the property has keyframes
        keyframe_count = timeline_item.GetKeyframeCount(property_name) or 0
        if keyframe_count == 0:
            return f"Error: No keyframes found for property '{property_name}'"

        # Check if there's a keyframe at the specified frame
        for i in range(keyframe_count):
            kf = timeline_item.GetKeyframeAtIndex(property_name, i)
            if kf["frame"] == frame:
                keyframe_index = i
                break

        if keyframe_index == -1:
            return f"Error: No keyframe found at frame {frame} for property '{property_name}'"

        if new_frame is not None:
            # Check if new frame is within the item's range
            start_frame = timeline_item.GetStart()
            end_frame = timeline_item.GetEnd()

            if new_frame < start_frame or new_frame > end_frame:
                return f"Error: New frame {new_frame} is outside the item's range ({start_frame} to {end_frame})"

            # Delete the keyframe at the current frame
            current_value = timeline_item.GetPropertyAtKeyframeIndex(property_name, keyframe_index)
            timeline_item.DeleteKeyframe(property_name, frame)

            # Add a new keyframe at the new frame position with the current value (or new value if specified)
            value = new_value if new_value is not None else current_value
            result = timeline_item.AddKeyframe(property_name, new_frame, value)

            if result:
                return f"Successfully moved keyframe for {property_name} from frame {frame} to frame {new_frame}"
            else:
                return f"Failed to move keyframe for {property_name}"
        else:
            # Only changing the value, not the frame position
            # We need to delete and re-add the keyframe with the new value
            timeline_item.DeleteKeyframe(property_name, frame)
            result = timeline_item.AddKeyframe(property_name, frame, new_value)

            if result:
                return f"Successfully updated keyframe value for {property_name} at frame {frame} to {new_value}"
            else:
                return f"Failed to update keyframe value for {property_name} at frame {frame}"

    except Exception as e:
        return f"Error modifying keyframe: {str(e)}"


@mcp.tool()
def set_keyframe_interpolation(timeline_item_id: str, property_name: str, frame: int, interpolation_type: str) -> str:
    """Set the interpolation type for a keyframe.

    Args:
    timeline_item_id: The ID of the timeline item
    property_name: The name of the property with keyframe
    frame: Frame position of the keyframe
    interpolation_type: Type of interpolation. Options: 'Linear', 'Bezier', 'Ease-In', 'Ease-Out'
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate interpolation type
    valid_interpolation_types = ["Linear", "Bezier", "Ease-In", "Ease-Out"]
    if interpolation_type not in valid_interpolation_types:
        return f"Error: Invalid interpolation type. Must be one of: {', '.join(valid_interpolation_types)}"

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
            return f"Error: Timeline item with ID '{timeline_item_id}' not found"

        # Check if the property has keyframes
        keyframe_count = timeline_item.GetKeyframeCount(property_name) or 0
        if keyframe_count == 0:
            return f"Error: No keyframes found for property '{property_name}'"

        # Check if there's a keyframe at the specified frame
        keyframe_exists = False
        for i in range(keyframe_count):
            kf = timeline_item.GetKeyframeAtIndex(property_name, i)
            if kf["frame"] == frame:
                keyframe_exists = True
                break

        if not keyframe_exists:
            return f"Error: No keyframe found at frame {frame} for property '{property_name}'"

        # Set the interpolation type
        interpolation_map = {"Linear": 0, "Bezier": 1, "Ease-In": 2, "Ease-Out": 3}

        # Get current keyframe value
        value = None
        for i in range(keyframe_count):
            kf = timeline_item.GetKeyframeAtIndex(property_name, i)
            if kf["frame"] == frame:
                value = timeline_item.GetPropertyAtKeyframeIndex(property_name, i)
                break

        # Delete the old keyframe
        timeline_item.DeleteKeyframe(property_name, frame)

        # Add a new keyframe with the same value but different interpolation
        result = timeline_item.AddKeyframe(property_name, frame, value, interpolation_map[interpolation_type])

        if result:
            return f"Successfully set interpolation for {property_name} keyframe at frame {frame} to {interpolation_type}"
        else:
            return f"Failed to set interpolation for {property_name} keyframe at frame {frame}"

    except Exception as e:
        return f"Error setting keyframe interpolation: {str(e)}"


@mcp.tool()
def set_timeline_item_audio(
    timeline_item_id: str,
    volume: float = None,
    pan: float = None,
    eq_enabled: bool = None,
) -> str:
    """Set audio properties for a timeline item.

        Args:
        timeline_item_id: The ID of the timeline item to modify
        volume: Optional volume level (usually 0.0 to 2.0, where 1.0 is unity gain)
        pan: Optional pan value (-1.0 to 1.0, where -1.0 is left, 0 is center, 1.0 is right)
        eq_enabled: Optional boolean to enable/disable EQ

        Note: Audio properties (Volume, Pan, AudioSyncOffset) are NOT supported by the
    Resolve Scripting API. TimelineItem.SetProperty() does not support audio data.
    """
    return "Error: Audio properties (Volume, Pan, AudioSyncOffset) are NOT supported by the Resolve Scripting API. TimelineItem.SetProperty() does not support audio data."


@mcp.tool()
def set_timeline_item_composite(timeline_item_id: str, composite_mode: str = None, opacity: float = None) -> str:
    """Set composite properties for a timeline item.

    Args:
    timeline_item_id: The ID of the timeline item to modify
    composite_mode: Optional composite mode to set (e.g., 'Normal', 'Add', 'Multiply')
    opacity: Optional opacity value to set (0.0 to 1.0)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate inputs
    if composite_mode is None and opacity is None:
        return "Error: Must specify at least one of composite_mode or opacity"

    # Valid composite modes
    valid_composite_modes = [
        "Normal",
        "Add",
        "Subtract",
        "Difference",
        "Multiply",
        "Screen",
        "Overlay",
        "Hardlight",
        "Softlight",
        "Darken",
        "Lighten",
        "ColorDodge",
        "ColorBurn",
        "Exclusion",
        "Hue",
        "Saturation",
        "Color",
        "Luminosity",
    ]

    if composite_mode and composite_mode not in valid_composite_modes:
        return f"Error: Invalid composite mode. Must be one of: {', '.join(valid_composite_modes)}"

    if opacity is not None and (opacity < 0.0 or opacity > 1.0):
        return "Error: Opacity must be between 0.0 and 1.0"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        if timeline_item.GetType() != "Video":
            return f"Error: Timeline item with ID '{timeline_item_id}' is not a video item"

        success = True

        # Set composite mode if specified
        if composite_mode:
            result = timeline_item.SetProperty("CompositeMode", composite_mode)
            if not result:
                success = False

        # Set opacity if specified
        if opacity is not None:
            result = timeline_item.SetProperty("Opacity", opacity)
            if not result:
                success = False

        if success:
            changes = []
            if composite_mode:
                changes.append(f"composite mode to '{composite_mode}'")
            if opacity is not None:
                changes.append(f"opacity to {opacity}")

            return f"Successfully set {' and '.join(changes)} for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to set some composite properties for timeline item '{timeline_item.GetName()}'"
    except Exception as e:
        return f"Error setting timeline item composite properties: {str(e)}"


@mcp.tool()
def set_timeline_item_crop(timeline_item_id: str, crop_type: str, crop_value: float) -> str:
    """Set a crop property for a timeline item.

    Args:
    timeline_item_id: The ID of the timeline item to modify
    crop_type: The type of crop to set. Options: 'Left', 'Right', 'Top', 'Bottom'
    crop_value: The value to set for the crop (typically 0.0 to 1.0)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate crop type
    valid_crop_types = ["Left", "Right", "Top", "Bottom"]

    if crop_type not in valid_crop_types:
        return f"Error: Invalid crop type. Must be one of: {', '.join(valid_crop_types)}"

    property_name = f"Crop{crop_type}"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        if timeline_item.GetType() != "Video":
            return f"Error: Timeline item with ID '{timeline_item_id}' is not a video item"

        # Set the property
        result = timeline_item.SetProperty(property_name, crop_value)
        if result:
            return f"Successfully set crop {crop_type.lower()} to {crop_value} for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to set crop {crop_type.lower()} for timeline item '{timeline_item.GetName()}'"
    except Exception as e:
        return f"Error setting timeline item crop: {str(e)}"


@mcp.tool()
def set_timeline_item_retime(timeline_item_id: str, speed: float = None, process: str = None) -> str:
    """Set retiming properties for a timeline item.

        Args:
        timeline_item_id: The ID of the timeline item to modify
    speed: Optional speed factor (e.g., 0.5 for 50%, 2.0 for 200%)
    process: Optional retime process. Options: 'NearestFrame', 'FrameBlend', 'OpticalFlow'
        Valid: "nearest" (0), "frame_blend" (2), "optical_flow" (3)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate inputs
    if speed is None and process is None:
        return "Error: Must specify at least one of speed or process"

    if speed is not None and speed <= 0:
        return "Error: Speed must be greater than 0"

    valid_processes = ["NearestFrame", "FrameBlend", "OpticalFlow"]
    if process and process not in valid_processes:
        return f"Error: Invalid retime process. Must be one of: {', '.join(valid_processes)}"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        success = True

        # Set speed if specified
        if speed is not None:
            result = timeline_item.SetProperty("Speed", speed)
            if not result:
                success = False

        # Set retime process if specified
        if process:
            result = timeline_item.SetProperty("RetimeProcess", process)
            if not result:
                success = False

        if success:
            changes = []
            if speed is not None:
                changes.append(f"speed to {speed}x")
            if process:
                changes.append(f"retime process to '{process}'")

            return f"Successfully set {' and '.join(changes)} for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to set some retime properties for timeline item '{timeline_item.GetName()}'"
    except Exception as e:
        return f"Error setting timeline item retime properties: {str(e)}"


@mcp.tool()
def set_timeline_item_stabilization(
    timeline_item_id: str,
    enabled: bool = None,
    method: str = None,
    strength: float = None,
) -> str:
    """Set stabilization properties for a timeline item.

    Args:
    timeline_item_id: The ID of the timeline item to modify
    enabled: Optional boolean to enable/disable stabilization
    method: Optional stabilization method. Options: 'Perspective', 'Similarity', 'Translation'
    strength: Optional strength value (0.0 to 1.0)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate inputs
    if enabled is None and method is None and strength is None:
        return "Error: Must specify at least one parameter to modify"

    valid_methods = ["Perspective", "Similarity", "Translation"]
    if method and method not in valid_methods:
        return f"Error: Invalid stabilization method. Must be one of: {', '.join(valid_methods)}"

    if strength is not None and (strength < 0.0 or strength > 1.0):
        return "Error: Strength must be between 0.0 and 1.0"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        if timeline_item.GetType() != "Video":
            return f"Error: Timeline item with ID '{timeline_item_id}' is not a video item"

        success = True

        # Set enabled if specified
        if enabled is not None:
            result = timeline_item.SetProperty("StabilizationEnable", 1 if enabled else 0)
            if not result:
                success = False

        # Set method if specified
        if method:
            result = timeline_item.SetProperty("StabilizationMethod", method)
            if not result:
                success = False

        # Set strength if specified
        if strength is not None:
            result = timeline_item.SetProperty("StabilizationStrength", strength)
            if not result:
                success = False

        if success:
            changes = []
            if enabled is not None:
                changes.append(f"stabilization {'enabled' if enabled else 'disabled'}")
            if method:
                changes.append(f"stabilization method to '{method}'")
            if strength is not None:
                changes.append(f"stabilization strength to {strength}")

            return f"Successfully set {' and '.join(changes)} for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to set some stabilization properties for timeline item '{timeline_item.GetName()}'"
    except Exception as e:
        return f"Error setting timeline item stabilization properties: {str(e)}"


@mcp.tool()
def set_timeline_item_transform(timeline_item_id: str, property_name: str, property_value: float) -> str:
    """Set a transform property for a timeline item.

    Args:
    timeline_item_id: The ID of the timeline item to modify
    property_name: The name of the property to set. Options include:
                  'Pan', 'Tilt', 'ZoomX', 'ZoomY', 'Rotation', 'AnchorPointX',
                  'AnchorPointY', 'Pitch', 'Yaw'
    property_value: The value to set for the property
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    # Validate property name
    valid_properties = [
        "Pan",
        "Tilt",
        "ZoomX",
        "ZoomY",
        "Rotation",
        "AnchorPointX",
        "AnchorPointY",
        "Pitch",
        "Yaw",
    ]

    if property_name not in valid_properties:
        return f"Error: Invalid property name. Must be one of: {', '.join(valid_properties)}"

    try:
        # Find the timeline item by ID
        video_track_count = current_timeline.GetTrackCount("video")

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

        if not timeline_item:
            return f"Error: Video timeline item with ID '{timeline_item_id}' not found"

        if timeline_item.GetType() != "Video":
            return f"Error: Timeline item with ID '{timeline_item_id}' is not a video item"

        # Set the property
        result = timeline_item.SetProperty(property_name, property_value)
        if result:
            return f"Successfully set {property_name} to {property_value} for timeline item '{timeline_item.GetName()}'"
        else:
            return f"Failed to set {property_name} for timeline item '{timeline_item.GetName()}'"
    except Exception as e:
        return f"Error setting timeline item property: {str(e)}"


@mcp.tool()
def ti_add_flag(color: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Add a flag to a timeline item.

    Args:
    color: Flag color.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.AddFlag(color))}


@mcp.tool()
def ti_add_fusion_comp(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Add a new Fusion composition to a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.AddFusionComp())}


@mcp.tool()
def ti_add_marker(
    frame_id: int,
    color: str,
    name: str,
    note: str = "",
    duration: int = 1,
    custom_data: str = "",
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Add a marker to a timeline item.

        Args:
        frame_id: Frame offset within the item.
    color: Marker color.
    name: Marker name.
    note: Marker note. Default: ''.
    duration: Duration in frames. Default: 1.
    custom_data: Custom data. Default: ''.
    item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    result = item.AddMarker(frame_id, color, name, note, duration, custom_data)
    return {"success": bool(result)}


@mcp.tool()
def ti_add_take(
    media_pool_item_id: str,
    start_frame: int = 0,
    end_frame: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Add a take to a timeline item.

    Args:
    media_pool_item_id: Unique ID of the MediaPoolItem to use as take.
    start_frame: Start frame. Default: 0.
    end_frame: End frame. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    _, mp, mp_err = _get_mp()
    if mp_err:
        return mp_err
    mpi = _find_clip_by_id(mp.GetRootFolder(), media_pool_item_id)
    if not mpi:
        return {"error": f"MediaPoolItem {media_pool_item_id} not found"}
    return {"success": bool(item.AddTake(mpi, start_frame, end_frame))}


@mcp.tool()
def ti_add_version(
    version_name: str,
    version_type: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Add a new color version to a timeline item.

    Args:
    version_name: Name for the new version.
    version_type: 0=Local, 1=Remote. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.AddVersion(version_name, version_type))}


@mcp.tool()
def ti_clear_clip_color(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Clear clip color from a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.ClearClipColor())}


@mcp.tool()
def ti_clear_flags(
    color: str = "",
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Clear flags from a timeline item.

    Args:
    color: Color to clear, or '' for all.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.ClearFlags(color))}


@mcp.tool()
def ti_create_magic_mask(
    mode: str = "Forward",
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Create a Magic Mask on a timeline item.

        Args:
        mode: 'Forward' or 'Backward'. Default: 'Forward'.
        Valid: "F" forward, "B" backward, "BI" bidirectional
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.CreateMagicMask(mode))}


@mcp.tool()
def ti_delete_fusion_comp(comp_name: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Delete a Fusion composition by name.

    Args:
    comp_name: Name of the Fusion composition.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteFusionCompByName(comp_name))}


@mcp.tool()
def ti_delete_marker_at_frame(frame_id: int, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Delete a marker at a frame on a timeline item.

    Args:
    frame_id: Frame number.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteMarkerAtFrame(frame_id))}


@mcp.tool()
def ti_delete_marker_by_custom_data(
    custom_data: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Delete a marker by custom data on a timeline item.

    Args:
    custom_data: Custom data of the marker.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteMarkerByCustomData(custom_data))}


@mcp.tool()
def ti_delete_markers_by_color(color: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Delete markers by color on a timeline item.

        Args:
        color: Color to delete. '' for all.
        Valid: Blue, Cyan, Green, Yellow, Red, Pink, Purple, Fuchsia, Rose, Lavender, SkyBlue, Mint, Lemon, Sand, Cocoa, Cream
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteMarkersByColor(color))}


@mcp.tool()
def ti_delete_take(
    take_index: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Delete a take by index.

    Args:
    take_index: 1-based take index.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteTakeByIndex(take_index))}


@mcp.tool()
def ti_delete_version(
    version_name: str,
    version_type: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Delete a color version.

    Args:
    version_name: Name of the version.
    version_type: 0=Local, 1=Remote. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.DeleteVersionByName(version_name, version_type))}


@mcp.tool()
def ti_export_fusion_comp(
    file_path: str,
    comp_index: int = 1,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Export a Fusion composition to file.

    Args:
    file_path: Output path for the .comp file.
    comp_index: 1-based Fusion comp index. Default: 1.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    comp = item.GetFusionCompByIndex(comp_index)
    if not comp:
        return {"error": f"No Fusion comp at index {comp_index}"}
    return {"success": bool(item.ExportFusionComp(file_path, comp_index))}


@mcp.tool()
def ti_export_lut(
    export_type: str,
    path: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Export LUT from a timeline item.

    Args:
    export_type: LUT type ('EXPORT_LUT_17PTCUBE', 'EXPORT_LUT_33PTCUBE', 'EXPORT_LUT_65PTCUBE', 'EXPORT_LUT_PANASONICVLUT').
    path: Output file path.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    try:
        etype = getattr(resolve, export_type) if hasattr(resolve, export_type) else export_type
    except Exception:
        etype = export_type
    return {"success": bool(item.ExportLUT(etype, path))}


@mcp.tool()
def ti_finalize_take(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Finalize the selected take.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.FinalizeTake())}


@mcp.tool()
def ti_get_cache_status(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get cache status for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {
        "color_output_cache_enabled": bool(item.GetIsColorOutputCacheEnabled()),
        "fusion_output_cache_enabled": bool(item.GetIsFusionOutputCacheEnabled()),
    }


@mcp.tool()
def ti_get_clip_color(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get clip color of a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"clip_color": item.GetClipColor() or ""}


@mcp.tool()
def ti_get_color_group(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get the color group for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    group = item.GetColorGroup()
    if group:
        return {"group_name": group.GetName()}
    return {"group_name": None}


@mcp.tool()
def ti_get_current_version(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get the current color version of a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"version": item.GetCurrentVersion() or {}}


@mcp.tool()
def ti_get_flag_list(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get flags on a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"flags": item.GetFlagList() or []}


@mcp.tool()
def ti_get_fusion_comp_info(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get Fusion composition info for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {
        "comp_count": item.GetFusionCompCount(),
        "comp_names": item.GetFusionCompNameList() or {},
    }


@mcp.tool()
def ti_get_info(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get comprehensive info about a timeline item.

        Args:
        item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {
        "name": item.GetName(),
        "duration": item.GetDuration(),
        "start": item.GetStart(),
        "end": item.GetEnd(),
        "left_offset": item.GetLeftOffset(),
        "right_offset": item.GetRightOffset(),
        "source_start_frame": item.GetSourceStartFrame(),
        "source_end_frame": item.GetSourceEndFrame(),
        "unique_id": item.GetUniqueId(),
        "clip_enabled": item.GetClipEnabled(),
    }


@mcp.tool()
def ti_get_linked_items(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get items linked to a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    linked = item.GetLinkedItems()
    if linked:
        return {"linked_items": [{"name": li.GetName(), "unique_id": li.GetUniqueId()} for li in linked]}
    return {"linked_items": []}


@mcp.tool()
def ti_get_marker_by_custom_data(
    custom_data: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Find marker by custom data.

    Args:
    custom_data: Custom data to search for.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"marker": item.GetMarkerByCustomData(custom_data) or {}}


@mcp.tool()
def ti_get_marker_custom_data(frame_id: int, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get marker custom data.

    Args:
    frame_id: Frame number.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"custom_data": item.GetMarkerCustomData(frame_id) or ""}


@mcp.tool()
def ti_get_markers(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get all markers on a timeline item.

        Args:
        item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"markers": item.GetMarkers() or {}}


@mcp.tool()
def ti_get_media_pool_item(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get the MediaPoolItem associated with a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    mpi = item.GetMediaPoolItem()
    if mpi:
        return {"name": mpi.GetName(), "unique_id": mpi.GetUniqueId()}
    return {"media_pool_item": None}


@mcp.tool()
def ti_get_node_graph(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get the color node graph for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    graph = item.GetNodeGraph()
    if graph:
        return {"has_graph": True, "num_nodes": graph.GetNumNodes()}
    return {"has_graph": False}


@mcp.tool()
def ti_get_property(
    property_name: str = "",
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get property of a timeline item.

        Args:
        property_name: Property name, or empty for all. Default: ''.
    item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    result = item.GetProperty(property_name) if property_name else item.GetProperty()
    return {"property": result}


@mcp.tool()
def ti_get_source_audio_channel_mapping(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get source audio channel mapping for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    mapping = item.GetSourceAudioChannelMapping()
    return {"audio_channel_mapping": mapping if mapping else ""}


@mcp.tool()
def ti_get_source_start_time(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get source start time of a timeline item.

        Args:
        item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {
        "source_start_time": item.GetSourceStartTime(),
        "source_end_time": item.GetSourceEndTime(),
    }


@mcp.tool()
def ti_get_stereo_convergence_values(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get stereo convergence values for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"convergence": item.GetStereoConvergenceValues() or {}}


@mcp.tool()
def ti_get_stereo_floating_window_params(
    eye: str = "left",
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get stereo floating window parameters.

    Args:
    eye: 'left' or 'right'. Default: 'left'.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    if eye == "left":
        return {"params": item.GetStereoLeftFloatingWindowParams() or {}}
    else:
        return {"params": item.GetStereoRightFloatingWindowParams() or {}}


@mcp.tool()
def ti_get_takes_info(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get takes info for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    count = item.GetTakesCount()
    selected = item.GetSelectedTakeIndex()
    takes = []
    for i in range(count):
        take = item.GetTakeByIndex(i + 1)
        takes.append(take if take else {})
    return {"takes_count": count, "selected_take_index": selected, "takes": takes}


@mcp.tool()
def ti_get_track_type_and_index(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Get the track type and index for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    result = item.GetTrackTypeAndIndex()
    return {
        "track_type": result[0] if result else "",
        "track_index": result[1] if result and len(result) > 1 else 0,
    }


@mcp.tool()
def ti_get_version_name_list(
    version_type: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Get list of version names.

    Args:
    version_type: 0=Local, 1=Remote. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"versions": item.GetVersionNameList(version_type) or []}


@mcp.tool()
def ti_import_fusion_comp(file_path: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Import a Fusion composition from file.

    Args:
    file_path: Path to the .comp file.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.ImportFusionComp(file_path))}


@mcp.tool()
def ti_load_burn_in_preset(
    preset_name: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Load a burn-in preset for a timeline item.

    Args:
    preset_name: Burn-in preset name.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.LoadBurnInPreset(preset_name))}


@mcp.tool()
def ti_load_fusion_comp(comp_name: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Load a Fusion composition by name.

    Args:
    comp_name: Name of the Fusion composition.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.LoadFusionCompByName(comp_name))}


@mcp.tool()
def ti_load_version(
    version_name: str,
    version_type: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Load a color version.

    Args:
    version_name: Name of the version.
    version_type: 0=Local, 1=Remote. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.LoadVersionByName(version_name, version_type))}


@mcp.tool()
def ti_regenerate_magic_mask(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Regenerate Magic Mask on a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.RegenerateMagicMask())}


@mcp.tool()
def ti_remove_from_color_group(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Remove a timeline item from its color group.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.RemoveFromColorGroup())}


@mcp.tool()
def ti_rename_fusion_comp(
    old_name: str,
    new_name: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Rename a Fusion composition.

    Args:
    old_name: Current name.
    new_name: New name.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.RenameFusionCompByName(old_name, new_name))}


@mcp.tool()
def ti_rename_version(
    old_name: str,
    new_name: str,
    version_type: int = 0,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Rename a color version.

    Args:
    old_name: Current version name.
    new_name: New version name.
    version_type: 0=Local, 1=Remote. Default: 0.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.RenameVersionByName(old_name, new_name, version_type))}


@mcp.tool()
def ti_select_take(
    take_index: int,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Select a take by index.

    Args:
    take_index: 1-based take index.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SelectTakeByIndex(take_index))}


@mcp.tool()
def ti_set_cdl(
    cdl: Dict[str, Any],
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Set CDL (Color Decision List) values on a timeline item.

    Args:
    cdl: Dict with CDL values: {'NodeIndex': str, 'Slope': str, 'Offset': str, 'Power': str, 'Saturation': str}.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SetCDL(cdl))}


@mcp.tool()
def ti_set_clip_color(color: str, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Set clip color of a timeline item.

    Args:
    color: Color name.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SetClipColor(color))}


@mcp.tool()
def ti_set_clip_enabled(enabled: bool, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Enable or disable a timeline item.

    Args:
    enabled: True to enable, False to disable.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SetClipEnabled(enabled))}


@mcp.tool()
def ti_set_color_output_cache(enabled: bool, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Enable/disable color output cache for a timeline item.

    Args:
    enabled: True to enable, False to disable.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SetColorOutputCache(enabled))}


@mcp.tool()
def ti_set_fusion_output_cache(enabled: bool, item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Enable/disable Fusion output cache for a timeline item.

    Args:
    enabled: True to enable, False to disable.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SetFusionOutputCache(enabled))}


@mcp.tool()
def ti_set_property(
    property_name: str,
    property_value: Any,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Set a property on a timeline item.

        Args:
        property_name: Property name (Pan, Tilt, ZoomX, ZoomY, RotationAngle, Opacity, CropLeft, CropRight, CropTop, CropBottom, etc.).
    property_value: Value to set.
    item_index: 0-based item index. Default: 0.
    track_type: 'video' or 'audio'. Default: 'video'.
        Valid: "video", "audio", "subtitle"
    track_index: 1-based track index. Default: 1.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    result = item.SetProperty(property_name, property_value)
    return {"success": bool(result)}


@mcp.tool()
def ti_smart_reframe(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Apply Smart Reframe to a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.SmartReframe())}


@mcp.tool()
def ti_stabilize(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Stabilize a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.Stabilize())}


@mcp.tool()
def ti_update_marker_custom_data(
    frame_id: int,
    custom_data: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Update marker custom data.

    Args:
    frame_id: Frame number.
    custom_data: New custom data.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.UpdateMarkerCustomData(frame_id, custom_data))}


@mcp.tool()
def ti_update_sidecar(item_index: int = 0, track_type: str = "video", track_index: int = 1) -> Dict[str, Any]:
    """Update sidecar file for a timeline item.

    Args:
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    return {"success": bool(item.UpdateSidecar())}


@mcp.tool()
def timeline_get_current_video_item() -> Dict[str, Any]:
    """Get the current video item at the playhead."""
    _, tl, err = _get_timeline()
    if err:
        return err
    item = tl.GetCurrentVideoItem()
    if item:
        return {
            "name": item.GetName(),
            "unique_id": item.GetUniqueId(),
            "start": item.GetStart(),
            "end": item.GetEnd(),
        }
    return {"item": None}
