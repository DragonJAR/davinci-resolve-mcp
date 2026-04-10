#!/usr/bin/env python3
"""Granular server — resolve_control tools."""

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
    open_preferences,
    open_project_settings,
    quit_resolve_app,
    restart_resolve_app,
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
    print_object_help,
)
from src.utils.project_properties import (
    get_all_project_properties,
    get_color_settings,
    get_project_info,
    get_project_metadata,
    get_project_property,
    get_superscale_settings,
    get_timeline_format_settings,
    set_color_space,
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
def add_items_to_media_pool_from_storage(file_paths: List[str]) -> Dict[str, Any]:
    """Add specified file/folder paths from Media Storage into current Media Pool folder.

    Args:
    file_paths: List of absolute file or folder paths to add to the Media Pool.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    ms = resolve.GetMediaStorage()
    if not ms:
        return {"error": "Failed to get MediaStorage"}
    clips = ms.AddItemListToMediaPool(file_paths)
    if clips:
        return {"success": True, "clips_added": len(clips)}
    return {"success": False, "error": "Failed to add items to Media Pool"}


@mcp.tool()
def add_render_job() -> Dict[str, Any]:
    """Add a render job based on current render settings to the render queue.

    Returns the unique job ID string for the new render job.
    Configure render settings first with set_render_settings, set_render_format_and_codec, etc.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    job_id = project.AddRenderJob()
    if job_id:
        return {"success": True, "job_id": job_id}
    return {
        "success": False,
        "error": "Failed to add render job. Check render settings are configured.",
    }


@mcp.tool()
def add_to_render_queue(preset_name: str, timeline_name: str = None, use_in_out_range: bool = False) -> Dict[str, Any]:
    """Add a timeline to the render queue with the specified preset.

    Args:
    preset_name: Name of the render preset to use
    timeline_name: Name of the timeline to render (uses current if None)
    use_in_out_range: Whether to render only the in/out range instead of entire timeline
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def apply_color_preset(
    preset_id: str = None,
    preset_name: str = None,
    clip_name: str = None,
    album_name: str = "DaVinci Resolve",
) -> str:
    """Apply a color preset to the specified clip.

    Args:
    preset_id: ID of the preset to apply (if known)
    preset_name: Name of the preset to apply (searches in album)
    clip_name: Name of the clip to apply preset to (uses current clip if None)
    album_name: Album containing the preset (default: "DaVinci Resolve")
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    if not preset_id and not preset_name:
        return "Error: Must provide either preset_id or preset_name"

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        return "Error: Failed to get Project Manager"

    current_project = project_manager.GetCurrentProject()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get the current timeline
        current_timeline = current_project.GetCurrentTimeline()
        if not current_timeline:
            return "Error: No timeline is currently open"

        # Get the specific clip or current clip
        if clip_name:
            # Find the clip by name in the timeline
            timeline_clips = current_timeline.GetItemListInTrack("video", 1)
            target_clip = None

            for clip in timeline_clips:
                if clip.GetName() == clip_name:
                    target_clip = clip
                    break

            if not target_clip:
                return f"Error: Clip '{clip_name}' not found in the timeline"

            # Select the clip
            current_timeline.SetCurrentSelectedItem(target_clip)

        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Find the album
        album = None
        albums = gallery.GetAlbums()

        if albums:
            for a in albums:
                if a.GetName() == album_name:
                    album = a
                    break

        if not album:
            return f"Error: Album '{album_name}' not found"

        # Find the still to apply
        stills = album.GetStills()
        if not stills:
            return f"Error: No presets found in album '{album_name}'"

        target_still = None

        if preset_id:
            # Find by ID
            for still in stills:
                if still.GetUniqueId() == preset_id:
                    target_still = still
                    break
        elif preset_name:
            # Find by name
            for still in stills:
                if still.GetLabel() == preset_name:
                    target_still = still
                    break

        if not target_still:
            search_term = preset_id if preset_id else preset_name
            return f"Error: Preset '{search_term}' not found in album '{album_name}'"

        # Apply the preset
        result = target_still.ApplyToClip()

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if result:
            return f"Successfully applied color preset to {'specified clip' if clip_name else 'current clip'}"
        else:
            return "Failed to apply color preset"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error applying color preset: {str(e)}"


@mcp.tool()
def apply_fairlight_preset(preset_name: str) -> str:
    """Apply a Fairlight audio preset to the current timeline.

    Args:
    preset_name: The name of the Fairlight preset to apply
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    try:
        result = current_project.ApplyFairlightPresetToCurrentTimeline(preset_name)
        if result:
            return f"Successfully applied Fairlight preset '{preset_name}'"
        else:
            return f"Failed to apply Fairlight preset '{preset_name}'"
    except Exception as e:
        return f"Error applying Fairlight preset: {str(e)}"


@mcp.tool()
def archive_project(
    project_name: str,
    archive_path: str,
    archive_src_media: bool = True,
    archive_render_cache: bool = True,
    archive_proxy_media: bool = False,
) -> Dict[str, Any]:
    """Archive a project to a file with optional media.

    Args:
    project_name: Name of the project to archive.
    archive_path: Absolute path for the archive file (.dra).
    archive_src_media: Include source media in archive. Default: True.
    archive_render_cache: Include render cache. Default: True.
    archive_proxy_media: Include proxy media. Default: False.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    try:
        archive_path = _validate_path(archive_path)
    except ValueError as e:
        return {"error": str(e)}
    pm = resolve.GetProjectManager()
    result = pm.ArchiveProject(
        project_name,
        archive_path,
        archive_src_media,
        archive_render_cache,
        archive_proxy_media,
    )
    return {
        "success": bool(result),
        "project_name": project_name,
        "archive_path": archive_path,
    }


@mcp.tool()
def auto_sync_audio(
    clip_names: List[str],
    sync_method: str = "waveform",
    append_mode: bool = False,
    target_bin: str = None,
) -> str:
    """Sync audio between clips with customizable settings.

    Args:
    clip_names: List of clip names to sync
    sync_method: Method to use for synchronization - 'waveform' or 'timecode'
    append_mode: Whether to append the audio or replace it
    target_bin: Optional bin to move synchronized clips to
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def clear_render_queue() -> Dict[str, Any]:
    """Clear all jobs from the render queue."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def copy_grade(source_clip_name: str = None, target_clip_name: str = None, mode: str = "full") -> str:
    """Copy a grade from one clip to another in the color page.

    Args:
    source_clip_name: Name of the source clip to copy grade from (uses current clip if None)
    target_clip_name: Name of the target clip to apply grade to (uses current clip if None)
    mode: What to copy - 'full' (entire grade), 'current_node', or 'all_nodes'
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def create_color_preset_album(album_name: str) -> str:
    """Create a new album for color presets.

    Args:
    album_name: Name for the new album
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Check if album already exists
        albums = gallery.GetAlbums()

        if albums:
            for a in albums:
                if a.GetName() == album_name:
                    # Return to the original page if we switched
                    if current_page != "color":
                        resolve.OpenPage(current_page)
                    return f"Album '{album_name}' already exists"

        # Create a new album
        album = gallery.CreateAlbum(album_name)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if album:
            return f"Successfully created album '{album_name}'"
        else:
            return f"Failed to create album '{album_name}'"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error creating album: {str(e)}"


@mcp.tool()
def create_project(name: str) -> str:
    """Create a new project with the given name.

    Args:
    name: The name for the new project
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    if not name:
        return "Error: Project name cannot be empty"

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        return "Error: Failed to get Project Manager"

    # Check if project already exists
    projects = project_manager.GetProjectListInCurrentFolder()
    if name in projects:
        return f"Error: Project '{name}' already exists"

    result = project_manager.CreateProject(name)
    if result:
        return f"Successfully created project '{name}'"
    else:
        return f"Failed to create project '{name}'"


@mcp.tool()
def create_project_folder(folder_name: str) -> Dict[str, Any]:
    """Create a new folder in the current project folder location.

    Args:
    folder_name: Name of the folder to create.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.CreateFolder(folder_name)
    return {"success": bool(result), "folder_name": folder_name}


@mcp.tool()
def create_timeline(name: str) -> str:
    """Create a new timeline with the given name.

    Args:
    name: The name for the new timeline
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

    media_pool = current_project.GetMediaPool()
    if not media_pool:
        return "Error: Failed to get Media Pool"

    timeline = media_pool.CreateEmptyTimeline(name)
    if timeline:
        return f"Successfully created timeline '{name}'"
    else:
        return f"Failed to create timeline '{name}'"


@mcp.tool()
def delete_color_preset(preset_id: str = None, preset_name: str = None, album_name: str = "DaVinci Resolve") -> str:
    """Delete a color preset.

    Args:
    preset_id: ID of the preset to delete (if known)
    preset_name: Name of the preset to delete (searches in album)
    album_name: Album containing the preset (default: "DaVinci Resolve")
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    if not preset_id and not preset_name:
        return "Error: Must provide either preset_id or preset_name"

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        return "Error: Failed to get Project Manager"

    current_project = project_manager.GetCurrentProject()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Find the album
        album = None
        albums = gallery.GetAlbums()

        if albums:
            for a in albums:
                if a.GetName() == album_name:
                    album = a
                    break

        if not album:
            return f"Error: Album '{album_name}' not found"

        # Find the still to delete
        stills = album.GetStills()
        if not stills:
            return f"Error: No presets found in album '{album_name}'"

        target_still = None

        if preset_id:
            # Find by ID
            for still in stills:
                if still.GetUniqueId() == preset_id:
                    target_still = still
                    break
        elif preset_name:
            # Find by name
            for still in stills:
                if still.GetLabel() == preset_name:
                    target_still = still
                    break

        if not target_still:
            search_term = preset_id if preset_id else preset_name
            return f"Error: Preset '{search_term}' not found in album '{album_name}'"

        # Delete the preset
        result = album.DeleteStill(target_still)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if result:
            return f"Successfully deleted color preset from album '{album_name}'"
        else:
            return "Failed to delete color preset"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error deleting color preset: {str(e)}"


@mcp.tool()
def delete_color_preset_album(album_name: str) -> str:
    """Delete a color preset album.

    Args:
    album_name: Name of the album to delete
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Find the album
        album = None
        albums = gallery.GetAlbums()

        if albums:
            for a in albums:
                if a.GetName() == album_name:
                    album = a
                    break

        if not album:
            # Return to the original page if we switched
            if current_page != "color":
                resolve.OpenPage(current_page)
            return f"Error: Album '{album_name}' not found"

        # Delete the album
        result = gallery.DeleteAlbum(album)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if result:
            return f"Successfully deleted album '{album_name}'"
        else:
            return f"Failed to delete album '{album_name}'"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error deleting album: {str(e)}"


@mcp.tool()
def delete_layout_preset_tool(preset_name: str) -> Dict[str, Any]:
    """Delete a layout preset.

    Calls Resolve.DeleteLayoutPreset() to remove a saved preset.

        Args:
        preset_name: Name of the preset to delete.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.DeleteLayoutPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def delete_project(project_name: str) -> Dict[str, Any]:
    """Delete a project from the current database. WARNING: This is irreversible.

    Args:
    project_name: Name of the project to delete.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.DeleteProject(project_name)
    return {"success": bool(result), "project_name": project_name}


@mcp.tool()
def delete_project_folder(folder_name: str) -> Dict[str, Any]:
    """Delete a folder from the current project folder location.

    Args:
    folder_name: Name of the folder to delete.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.DeleteFolder(folder_name)
    return {"success": bool(result), "folder_name": folder_name}


@mcp.tool()
def delete_render_job(job_id: str) -> Dict[str, Any]:
    """Delete a specific render job by its ID.

    Args:
    job_id: The unique ID of the render job to delete.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.DeleteRenderJob(job_id)
    return {"success": bool(result), "job_id": job_id}


@mcp.tool()
def delete_render_preset(preset_name: str) -> Dict[str, Any]:
    """Delete a render preset.

    Args:
    preset_name: Name of the render preset to delete.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.DeleteRenderPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def export_all_powergrade_luts(export_dir: str) -> str:
    """Export all PowerGrade presets as LUT files.

    Args:
    export_dir: Directory to save the exported LUTs
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Get PowerGrade album
        powergrade_album = None
        albums = gallery.GetAlbums()

        if albums:
            for album in albums:
                if album.GetName() == "PowerGrade":
                    powergrade_album = album
                    break

        if not powergrade_album:
            return "Error: PowerGrade album not found"

        # Get all stills in the PowerGrade album
        stills = powergrade_album.GetStills()
        if not stills:
            return "Error: No stills found in PowerGrade album"

        # Get current timeline for clip operations
        current_timeline = current_project.GetCurrentTimeline()

        # Create export directory if it doesn't exist
        if not os.path.exists(export_dir):
            os.makedirs(export_dir, exist_ok=True)

        # Export each still as a LUT
        exported_count = 0
        failed_stills = []

        for still in stills:
            still_name = still.GetLabel()
            if not still_name:
                still_name = f"PowerGrade_{still.GetUniqueId()}"

            # Create safe filename
            safe_name = "".join(c if c.isalnum() or c in ["-", "_"] else "_" for c in still_name)
            lut_path = os.path.join(export_dir, f"{safe_name}.cube")

            # Apply the still to the current clip
            current_clip = current_timeline.GetCurrentVideoItem()
            if not current_clip:
                failed_stills.append(f"{still_name} (no clip selected)")
                continue

            # Apply the grade from the still
            applied = still.ApplyToClip()
            if not applied:
                failed_stills.append(f"{still_name} (could not apply grade)")
                continue

            # Export as LUT
            result = current_project.ExportCurrentGradeAsLUT(0, 1, lut_path)  # Cube format, 33-point

            if result:
                exported_count += 1
            else:
                failed_stills.append(f"{still_name} (export failed)")

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if failed_stills:
            return f"Exported {exported_count} LUTs to '{export_dir}'. Failed to export: {', '.join(failed_stills)}"
        else:
            return f"Successfully exported all {exported_count} PowerGrade LUTs to '{export_dir}'"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error exporting PowerGrade LUTs: {str(e)}"


@mcp.tool()
def export_burn_in_preset(preset_name: str, export_path: str) -> Dict[str, Any]:
    """Export a burn-in preset to a file.

    Args:
    preset_name: Name of the burn-in preset to export.
    export_path: Absolute path where the preset file will be saved.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.ExportBurnInPreset(preset_name, export_path)
    return {
        "success": bool(result),
        "preset_name": preset_name,
        "export_path": export_path,
    }


@mcp.tool()
def export_current_frame_as_still(file_path: str) -> Dict[str, Any]:
    """Export the current frame as a still image.

    Args:
    file_path: Absolute path for the exported still image.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.ExportCurrentFrameAsStill(file_path)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def export_layout_preset_tool(preset_name: str, export_path: str) -> Dict[str, Any]:
    """Export a layout preset to a file.

    Calls Resolve.ExportLayoutPreset() to export a preset to disk.

        Args:
        preset_name: Name of the preset to export.
        export_path: Absolute file path to export the preset to.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.ExportLayoutPreset(preset_name, export_path)
    return {
        "success": bool(result),
        "preset_name": preset_name,
        "export_path": export_path,
    }


@mcp.tool()
def export_lut(
    clip_name: str = None,
    export_path: str = None,
    lut_format: str = "Cube",
    lut_size: str = "33Point",
) -> str:
    """Export a LUT from the current clip's grade.

    Args:
    clip_name: Name of the clip to export grade from (uses current clip if None)
    export_path: Path to save the LUT file (generated if None)
    lut_format: Format of the LUT. Options: 'Cube', 'Davinci', '3dl', 'Panasonic'
    lut_size: Size of the LUT. Options: '17Point', '33Point', '65Point'
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get the current timeline
        current_timeline = current_project.GetCurrentTimeline()
        if not current_timeline:
            return "Error: No timeline is currently open"

        # Get the specific clip or current clip
        if clip_name:
            # Find the clip by name in the timeline
            timeline_clips = current_timeline.GetItemListInTrack("video", 1)
            target_clip = None

            for clip in timeline_clips:
                if clip.GetName() == clip_name:
                    target_clip = clip
                    break

            if not target_clip:
                return f"Error: Clip '{clip_name}' not found in the timeline"

            # Select the clip
            current_timeline.SetCurrentSelectedItem(target_clip)

        # Generate export path if not provided
        if not export_path:
            clip_name_safe = clip_name if clip_name else "current_clip"
            clip_name_safe = clip_name_safe.replace(" ", "_").replace(":", "-")

            extension = ".cube"
            if lut_format.lower() == "davinci":
                extension = ".ilut"
            elif lut_format.lower() == "3dl":
                extension = ".3dl"
            elif lut_format.lower() == "panasonic":
                extension = ".vlut"

            safe_dir = _resolve_safe_dir(tempfile.gettempdir())
            os.makedirs(safe_dir, exist_ok=True)
            export_path = os.path.join(safe_dir, f"{clip_name_safe}_lut{extension}")

        # Validate LUT format
        valid_formats = ["Cube", "Davinci", "3dl", "Panasonic"]
        if lut_format not in valid_formats:
            return f"Error: Invalid LUT format. Must be one of: {', '.join(valid_formats)}"

        # Validate LUT size
        valid_sizes = ["17Point", "33Point", "65Point"]
        if lut_size not in valid_sizes:
            return f"Error: Invalid LUT size. Must be one of: {', '.join(valid_sizes)}"

        # Map format string to numeric value expected by DaVinci Resolve API
        format_map = {"Cube": 0, "Davinci": 1, "3dl": 2, "Panasonic": 3}

        # Map size string to numeric value
        size_map = {"17Point": 0, "33Point": 1, "65Point": 2}

        # Get current clip
        current_clip = current_timeline.GetCurrentVideoItem()
        if not current_clip:
            return "Error: No clip is currently selected"

        # Create a directory for the export path if it doesn't exist
        export_dir = os.path.dirname(export_path)
        if export_dir and not os.path.exists(export_dir):
            os.makedirs(export_dir, exist_ok=True)

        # Export the LUT
        colorpage = resolve.GetCurrentPage() == "color"
        if not colorpage:
            resolve.OpenPage("color")

        # Access Color page functionality
        result = current_project.ExportCurrentGradeAsLUT(format_map[lut_format], size_map[lut_size], export_path)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        if result:
            return f"Successfully exported LUT to '{export_path}' in {lut_format} format with {lut_size} size"
        else:
            return "Failed to export LUT"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error exporting LUT: {str(e)}"


@mcp.tool()
def export_project_to_file(project_name: str, file_path: str, with_stills_and_luts: bool = True) -> Dict[str, Any]:
    """Export a project to a .drp file.

    Args:
    project_name: Name of the project to export.
    file_path: Absolute path for the exported .drp file.
    with_stills_and_luts: Include stills and LUTs in export. Default: True.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    try:
        file_path = _validate_path(file_path)
    except ValueError as e:
        return {"error": str(e)}
    pm = resolve.GetProjectManager()
    result = pm.ExportProject(project_name, file_path, with_stills_and_luts)
    return {
        "success": bool(result),
        "project_name": project_name,
        "file_path": file_path,
    }


@mcp.tool()
def export_render_preset(preset_name: str, export_path: str) -> Dict[str, Any]:
    """Export a render preset to a file.

    Args:
    preset_name: Name of the render preset to export.
    export_path: Absolute path where the preset file will be saved.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.ExportRenderPreset(preset_name, export_path)
    return {
        "success": bool(result),
        "preset_name": preset_name,
        "export_path": export_path,
    }


@mcp.tool()
def get_color_group_clips(group_name: str) -> Dict[str, Any]:
    """Get clips in a color group for the current timeline.

    Args:
    group_name: Name of the color group.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    groups = project.GetColorGroupsList()
    target = None
    if groups:
        for g in groups:
            if g.GetName() == group_name:
                target = g
                break
    if not target:
        return {"error": f"Color group '{group_name}' not found"}
    clips = target.GetClipsInTimeline()
    if clips:
        return {"group": group_name, "clips": [{"name": c.GetName()} for c in clips]}
    return {"group": group_name, "clips": []}


@mcp.tool()
def get_color_group_post_clip_node_graph(group_name: str) -> Dict[str, Any]:
    """Get the post-clip node graph for a color group.

    Args:
    group_name: Name of the color group.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    groups = project.GetColorGroupsList()
    target = None
    if groups:
        for g in groups:
            if g.GetName() == group_name:
                target = g
                break
    if not target:
        return {"error": f"Color group '{group_name}' not found"}
    graph = target.GetPostClipNodeGraph()
    if graph:
        return {
            "group": group_name,
            "graph_type": "post_clip",
            "num_nodes": graph.GetNumNodes(),
        }
    return {"error": "No post-clip node graph available"}


@mcp.tool()
def get_color_group_pre_clip_node_graph(group_name: str) -> Dict[str, Any]:
    """Get the pre-clip node graph for a color group.

    Args:
    group_name: Name of the color group.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    groups = project.GetColorGroupsList()
    target = None
    if groups:
        for g in groups:
            if g.GetName() == group_name:
                target = g
                break
    if not target:
        return {"error": f"Color group '{group_name}' not found"}
    graph = target.GetPreClipNodeGraph()
    if graph:
        return {
            "group": group_name,
            "graph_type": "pre_clip",
            "num_nodes": graph.GetNumNodes(),
        }
    return {"error": "No pre-clip node graph available"}


@mcp.tool()
def get_current_database() -> Dict[str, Any]:
    """Get information about the current database."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    db = pm.GetCurrentDatabase()
    return db if db else {"error": "Failed to get current database"}


@mcp.tool()
def get_current_project_folder() -> Dict[str, Any]:
    """Get the name of the current project folder."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    folder = pm.GetCurrentFolder()
    return {"current_folder": folder}


@mcp.tool()
def get_current_render_format_and_codec() -> Dict[str, Any]:
    """Get the current render format and codec setting."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.GetCurrentRenderFormatAndCodec()
    return result if result else {"error": "Failed to get render format and codec"}


@mcp.tool()
def get_current_render_mode() -> Dict[str, Any]:
    """Get the current render mode (0=Individual Clips, 1=Single Clip)."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    mode = project.GetCurrentRenderMode()
    return {
        "render_mode": mode,
        "mode_name": "Individual Clips" if mode == 0 else "Single Clip",
    }


@mcp.tool()
def get_current_still_album() -> Dict[str, Any]:
    """Get the current still album."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    gallery = project.GetGallery()
    if not gallery:
        return {"error": "Failed to get Gallery"}
    album = gallery.GetCurrentStillAlbum()
    return {"has_album": album is not None}


@mcp.tool()
def get_database_list() -> Dict[str, Any]:
    """Get list of all available databases."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    dbs = pm.GetDatabaseList()
    return {"databases": dbs if dbs else []}


@mcp.tool()
def get_fairlight_presets() -> Dict[str, Any]:
    """Get Fairlight audio presets from DaVinci Resolve."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}

    try:
        presets = resolve.GetFairlightPresets()
        return {"presets": _serialize_value(presets)}
    except Exception as e:
        return {"error": f"Failed to get Fairlight presets: {str(e)}"}


@mcp.tool()
def get_fusion_object() -> Dict[str, Any]:
    """Get the Fusion object. Starting point for Fusion scripts."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    fusion = resolve.Fusion()
    if fusion:
        return {"success": True, "fusion_available": True}
    return {"success": False, "fusion_available": False}


@mcp.tool()
def get_gallery_album_name() -> Dict[str, Any]:
    """Get the name of the current gallery album."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    gallery = project.GetGallery()
    if not gallery:
        return {"error": "Failed to get Gallery"}
    name = gallery.GetAlbumName()
    return {"album_name": name if name else ""}


@mcp.tool()
def get_gallery_power_grade_albums() -> Dict[str, Any]:
    """Get list of all gallery power grade albums."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    gallery = project.GetGallery()
    if not gallery:
        return {"error": "Failed to get Gallery"}
    albums = gallery.GetGalleryPowerGradeAlbums()
    return {"albums": [str(a) for a in albums] if albums else []}


@mcp.tool()
def get_gallery_still_albums() -> Dict[str, Any]:
    """Get list of all gallery still albums."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    gallery = project.GetGallery()
    if not gallery:
        return {"error": "Failed to get Gallery"}
    albums = gallery.GetGalleryStillAlbums()
    return {"albums": [str(a) for a in albums] if albums else []}


@mcp.tool()
def get_keyframe_mode() -> Dict[str, Any]:
    """Get the current keyframe mode in Resolve."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    mode = resolve.GetKeyframeMode()
    mode_names = {0: "Linear", 1: "Bezier", 2: "Constant"}
    return {
        "mode": mode,
        "mode_name": mode_names.get(mode, "Unknown") if mode is not None else None,
        "note": "None means default project keyframe mode",
    }


@mcp.tool()
def get_media_storage_files(folder_path: str) -> Dict[str, Any]:
    """Get media and file listings in a given absolute folder path from Media Storage.

    Args:
    folder_path: Absolute path to the folder to list files for.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    ms = resolve.GetMediaStorage()
    if not ms:
        return {"error": "Failed to get MediaStorage"}
    files = ms.GetFileList(folder_path)
    return {"folder_path": folder_path, "files": files if files else []}


@mcp.tool()
def get_media_storage_subfolders(folder_path: str) -> Dict[str, Any]:
    """Get subfolders in a given absolute folder path from Media Storage.

    Args:
    folder_path: Absolute path to the folder to list subfolders for.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    ms = resolve.GetMediaStorage()
    if not ms:
        return {"error": "Failed to get MediaStorage"}
    subfolders = ms.GetSubFolderList(folder_path)
    return {"folder_path": folder_path, "subfolders": subfolders if subfolders else []}


@mcp.tool()
def get_mounted_volumes() -> Dict[str, Any]:
    """Get list of mounted volumes displayed in Resolve's Media Storage."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    ms = resolve.GetMediaStorage()
    if not ms:
        return {"error": "Failed to get MediaStorage"}
    volumes = ms.GetMountedVolumeList()
    return {"volumes": volumes if volumes else []}


@mcp.tool()
def get_project_folder_list() -> Dict[str, Any]:
    """Get list of folders in the current project folder location."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    folders = pm.GetFolderListInCurrentFolder()
    return {"folders": folders if folders else []}


@mcp.tool()
def get_project_preset_list() -> Dict[str, Any]:
    """Get list of available project presets."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    presets = project.GetPresetList()
    return {"presets": presets if presets else []}


@mcp.tool()
def get_quick_export_render_presets() -> Dict[str, Any]:
    """Get list of available quick export render presets."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    presets = project.GetQuickExportRenderPresets()
    return {"presets": presets if presets else []}


@mcp.tool()
def get_render_formats() -> Dict[str, Any]:
    """Get all available render formats."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    formats = project.GetRenderFormats()
    return {"formats": formats if formats else {}}


@mcp.tool()
def get_render_job_list() -> Dict[str, Any]:
    """Get list of all render jobs in the queue."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    jobs = project.GetRenderJobList()
    return {"render_jobs": jobs if jobs else []}


@mcp.tool()
def get_render_job_status(job_id: str) -> Dict[str, Any]:
    """Get the status of a specific render job.

    Args:
    job_id: The unique ID of the render job.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    status = project.GetRenderJobStatus(job_id)
    return status if status else {"error": f"No render job with ID {job_id}"}


@mcp.tool()
def get_render_resolutions(format_name: str, codec_name: str) -> Dict[str, Any]:
    """Get available render resolutions for a format/codec combination.

    Args:
    format_name: Render format (e.g. 'mp4').
    codec_name: Codec name (e.g. 'H264').
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    resolutions = project.GetRenderResolutions(format_name, codec_name)
    return {
        "format": format_name,
        "codec": codec_name,
        "resolutions": resolutions if resolutions else [],
    }


@mcp.tool()
def get_resolve_version_fields() -> Dict[str, Any]:
    """Get DaVinci Resolve version as structured fields [major, minor, patch, build, suffix]."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    version = resolve.GetVersion()
    if version:
        return {
            "major": version[0],
            "minor": version[1],
            "patch": version[2],
            "build": version[3],
            "suffix": version[4] if len(version) > 4 else "",
        }
    return {"error": "Failed to get version"}


@mcp.tool()
def get_voice_isolation_state(track_index: int = 1) -> Dict[str, Any]:
    """Get voice isolation state for a specific track.

    Args:
    track_index: The index of the track to get voice isolation state for (1-based index, defaults to 1)
    """
    pm, current_project = get_current_project()
    if not current_project:
        return {"error": "No project currently open"}

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return {"error": "No timeline currently active"}

    try:
        state = current_timeline.GetVoiceIsolationState(track_index)
        return _serialize_value(state)
    except Exception as e:
        return {"error": f"Failed to get voice isolation state: {str(e)}"}


@mcp.tool()
def goto_parent_project_folder() -> Dict[str, Any]:
    """Navigate up one level in the project folder hierarchy."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.GotoParentFolder()
    return {"success": bool(result)}


@mcp.tool()
def goto_root_project_folder() -> Dict[str, Any]:
    """Navigate to the root project folder."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.GotoRootFolder()
    return {"success": bool(result)}


@mcp.tool()
def import_burn_in_preset(preset_path: str) -> Dict[str, Any]:
    """Import a burn-in preset from a file.

    Args:
    preset_path: Absolute path to the burn-in preset file.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.ImportBurnInPreset(preset_path)
    return {"success": bool(result), "preset_path": preset_path}


@mcp.tool()
def import_layout_preset_tool(import_path: str, preset_name: str = None) -> Dict[str, Any]:
    """Import a layout preset from a file.

    Calls Resolve.ImportLayoutPreset() to import a preset from disk.

        Args:
        import_path: Absolute path to the preset file to import.
        preset_name: Name to save the imported preset as (uses filename if None).
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    if preset_name:
        result = resolve.ImportLayoutPreset(import_path, preset_name)
    else:
        result = resolve.ImportLayoutPreset(import_path)
        preset_name = os.path.splitext(os.path.basename(import_path))[0]
    return {
        "success": bool(result),
        "preset_name": preset_name,
        "import_path": import_path,
    }


@mcp.tool()
def import_project_from_file(file_path: str) -> Dict[str, Any]:
    """Import a project from a .drp file.

    Args:
    file_path: Absolute path to the .drp project file.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    try:
        file_path = _validate_path(file_path)
    except ValueError as e:
        return {"error": str(e)}
    pm = resolve.GetProjectManager()
    result = pm.ImportProject(file_path)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def import_render_preset(preset_path: str) -> Dict[str, Any]:
    """Import a render preset from a file.

    Args:
    preset_path: Absolute path to the render preset file.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.ImportRenderPreset(preset_path)
    return {"success": bool(result), "preset_path": preset_path}


@mcp.tool()
def insert_audio_to_current_track(file_path: str) -> Dict[str, Any]:
    """Insert audio file to current track at playhead position.

    Args:
    file_path: Absolute path to the audio file.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.InsertAudioToCurrentTrackAtPlayhead(file_path)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def inspect_custom_object(object_path: str) -> Dict[str, Any]:
    """
    Inspect a custom DaVinci Resolve API object by path.

        Args:
        object_path: Path to the object using dot notation (e.g., 'resolve.GetMediaStorage()')
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}

    try:
        # Start with resolve object
        obj = resolve

        # Split the path and traverse down
        parts = object_path.split(".")

        # Skip the first part if it's 'resolve'
        start_index = 1 if parts[0].lower() == "resolve" else 0

        for i in range(start_index, len(parts)):
            part = parts[i]

            # Check if it's a method call
            if part.endswith("()"):
                method_name = part[:-2]
                if hasattr(obj, method_name) and callable(getattr(obj, method_name)):
                    obj = getattr(obj, method_name)()
                else:
                    return {"error": f"Method '{method_name}' not found or not callable"}
            else:
                # It's an attribute access
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    return {"error": f"Attribute '{part}' not found"}

        # Inspect the object we've retrieved
        return inspect_object(obj)
    except Exception as e:
        return {"error": f"Error inspecting object: {str(e)}"}


@mcp.tool()
def is_rendering_in_progress() -> Dict[str, Any]:
    """Check if rendering is currently in progress."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.IsRenderingInProgress()
    return {"is_rendering": bool(result)}


@mcp.tool()
def link_proxy_media(clip_name: str, proxy_file_path: str) -> str:
    """Link a proxy media file to a clip.

    Args:
    clip_name: Name of the clip to link proxy to
    proxy_file_path: Path to the proxy media file
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
    if not os.path.exists(proxy_file_path):
        return f"Error: Proxy file '{proxy_file_path}' does not exist"

    try:
        result = target_clip.LinkProxyMedia(proxy_file_path)
        if result:
            return f"Successfully linked proxy media '{proxy_file_path}' to clip '{clip_name}'"
        else:
            return f"Failed to link proxy media to clip '{clip_name}'"
    except Exception as e:
        return f"Error linking proxy media: {str(e)}"


@mcp.tool()
def list_properties():
    """Lists all 26 valid TimelineItem property keys from the Resolve Scripting API."""
    video_props = [
        "Pan",
        "Tilt",
        "ZoomX",
        "ZoomY",
        "ZoomGang",
        "RotationAngle",
        "AnchorPointX",
        "AnchorPointY",
        "Pitch",
        "Yaw",
        "FlipX",
        "FlipY",
    ]
    composite_props = ["CompositeMode", "Opacity", "Distortion"]
    crop_props = [
        "CropLeft",
        "CropRight",
        "CropTop",
        "CropBottom",
        "CropSoftness",
        "CropRetain",
    ]
    retime_props = ["RetimeProcess", "MotionEstimation", "Scaling", "ResizeFilter"]
    misc_props = ["DynamicZoomEase"]
    return {
        "properties": {
            "video_transform": video_props,
            "composite": composite_props,
            "crop": crop_props,
            "retime": retime_props,
            "misc": misc_props,
            "all": video_props + composite_props + crop_props + retime_props + misc_props,
        },
        "count": 26,
        "note": "These 26 keys are valid for GetProperty(key) and SetProperty(key, value)",
    }


@mcp.tool()
def load_cloud_project(project_name: str, project_media_path: str, sync_mode: str = "proxy") -> Dict[str, Any]:
    """Load a cloud project from DaVinci Resolve cloud.

    Args:
    project_name: Name of the cloud project to load.
    project_media_path: Local path for project media cache.
    sync_mode: Sync mode - 'proxy' or 'full' (default: 'proxy').
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    if not pm:
        return {"error": "Failed to get ProjectManager"}
    cloud_settings = {
        resolve.CLOUD_SETTING_PROJECT_NAME: project_name,
        resolve.CLOUD_SETTING_PROJECT_MEDIA_PATH: project_media_path,
        resolve.CLOUD_SETTING_SYNC_MODE: sync_mode,
    }
    project = pm.LoadCloudProject(cloud_settings)
    if project:
        return {"success": True, "project_name": project.GetName()}
    return {
        "success": False,
        "error": "Failed to load cloud project. Check cloud settings and connectivity.",
    }


@mcp.tool()
def load_layout_preset_tool(preset_name: str) -> Dict[str, Any]:
    """Load a UI layout preset.

    Calls Resolve.LoadLayoutPreset() to load a saved UI layout.

        Args:
        preset_name: Name of the preset to load.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.LoadLayoutPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def load_render_preset(preset_name: str) -> Dict[str, Any]:
    """Load a render preset by name.

    Args:
    preset_name: Name of the render preset to load.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.LoadRenderPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def object_help(object_type: str) -> str:
    """
    Get human-readable help for a DaVinci Resolve API object.

        Args:
        object_type: Type of object to get help for ('resolve', 'project_manager',
                     'project', 'media_pool', 'timeline', 'media_storage')
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    # Map object type string to actual object
    obj = None

    if object_type == "resolve":
        obj = resolve
    elif object_type == "project_manager":
        obj = resolve.GetProjectManager()
    elif object_type == "project":
        pm = resolve.GetProjectManager()
        if pm:
            obj = pm.GetCurrentProject()
    elif object_type == "media_pool":
        pm = resolve.GetProjectManager()
        if pm:
            project = pm.GetCurrentProject()
            if project:
                obj = project.GetMediaPool()
    elif object_type == "timeline":
        pm = resolve.GetProjectManager()
        if pm:
            project = pm.GetCurrentProject()
            if project:
                obj = project.GetCurrentTimeline()
    elif object_type == "media_storage":
        obj = resolve.GetMediaStorage()
    else:
        return f"Error: Unknown object type '{object_type}'"

    if obj is None:
        return f"Error: Failed to get {object_type} object"

    # Generate and return help text
    return print_object_help(obj)


@mcp.tool()
def open_app_preferences() -> str:
    """Open the Preferences dialog in DaVinci Resolve."""
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    result = open_preferences(resolve)

    if result:
        return "Preferences dialog opened successfully"
    else:
        return "Failed to open Preferences dialog"


@mcp.tool()
def open_project(name: str) -> str:
    """Open a project by name.

    Args:
    name: The name of the project to open
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    if not name:
        return "Error: Project name cannot be empty"

    project_manager = resolve.GetProjectManager()
    if not project_manager:
        return "Error: Failed to get Project Manager"

    # Check if project exists
    projects = project_manager.GetProjectListInCurrentFolder()
    if name not in projects:
        return f"Error: Project '{name}' not found. Available projects: {', '.join(projects)}"

    result = project_manager.LoadProject(name)
    if result:
        return f"Successfully opened project '{name}'"
    else:
        return f"Failed to open project '{name}'"


@mcp.tool()
def open_project_folder(folder_name: str) -> Dict[str, Any]:
    """Open/navigate into a project folder.

    Args:
    folder_name: Name of the folder to open.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.OpenFolder(folder_name)
    return {"success": bool(result), "folder_name": folder_name}


@mcp.tool()
def open_settings() -> str:
    """Open the Project Settings dialog in DaVinci Resolve."""
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    result = open_project_settings(resolve)

    if result:
        return "Project Settings dialog opened successfully"
    else:
        return "Failed to open Project Settings dialog"


@mcp.tool()
def quit_app(force: bool = False, save_project: bool = True) -> str:
    """
    Quit DaVinci Resolve application.

        Args:
        force: Whether to force quit even if unsaved changes (potentially dangerous)
        save_project: Whether to save the project before quitting
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    result = quit_resolve_app(resolve, force, save_project)

    if result:
        return "DaVinci Resolve quit command sent successfully"
    else:
        return "Failed to quit DaVinci Resolve"


@mcp.tool()
def quit_resolve() -> Dict[str, Any]:
    """Quit DaVinci Resolve. WARNING: This will close the application."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    resolve.Quit()
    return {"success": True, "message": "DaVinci Resolve is quitting"}


@mcp.tool()
def render_with_quick_export(preset_name: str) -> Dict[str, Any]:
    """Render the current timeline using a Quick Export preset.

    Args:
    preset_name: Name of the Quick Export preset (e.g. 'H.264', 'YouTube', 'Vimeo').
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.RenderWithQuickExport(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def resolve_constants_all():
    """Get all API constants organized by category."""
    return {"categories": ALL_CONSTANTS}


@mcp.tool()
def resolve_constants_get(category: str):
    """Get constants for a specific category."""
    if category not in ALL_CONSTANTS:
        return {"error": f"Unknown category: {category}. Use resolve_constants_list_categories to see available."}
    return {"category": category, "constants": ALL_CONSTANTS[category]}


@mcp.tool()
def resolve_constants_list_categories():
    """List all API constant categories."""
    return {"categories": list(ALL_CONSTANTS.keys())}


@mcp.tool()
def restart_app(wait_seconds: int = 5) -> str:
    """
    Restart DaVinci Resolve application.

        Args:
        wait_seconds: Seconds to wait between quit and restart
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    result = restart_resolve_app(resolve, wait_seconds)

    if result:
        return "DaVinci Resolve restart initiated successfully"
    else:
        return "Failed to restart DaVinci Resolve"


@mcp.tool()
def restore_project(file_path: str) -> Dict[str, Any]:
    """Restore a project from an archive (.dra) file.

    Args:
    file_path: Absolute path to the .dra archive file.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    try:
        file_path = _validate_path(file_path)
    except ValueError as e:
        return {"error": str(e)}
    pm = resolve.GetProjectManager()
    result = pm.RestoreProject(file_path)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def reveal_in_media_storage(file_path: str) -> Dict[str, Any]:
    """Reveal a file path in Resolve's Media Storage browser.

    Args:
    file_path: Absolute path to the file to reveal.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    ms = resolve.GetMediaStorage()
    if not ms:
        return {"error": "Failed to get MediaStorage"}
    result = ms.RevealInStorage(file_path)
    return {"success": bool(result), "file_path": file_path}


@mcp.tool()
def save_as_new_render_preset(preset_name: str) -> Dict[str, Any]:
    """Save current render settings as a new preset.

    Args:
    preset_name: Name for the new render preset.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.SaveAsNewRenderPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def save_color_preset(clip_name: str = None, preset_name: str = None, album_name: str = "DaVinci Resolve") -> str:
    """Save a color preset from the specified clip.

    Args:
    clip_name: Name of the clip to save preset from (uses current clip if None)
    preset_name: Name to give the preset (uses clip name if None)
    album_name: Album to save the preset to (default: "DaVinci Resolve")
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Switch to color page
    current_page = resolve.GetCurrentPage()
    if current_page != "color":
        resolve.OpenPage("color")

    try:
        # Get the current timeline
        current_timeline = current_project.GetCurrentTimeline()
        if not current_timeline:
            return "Error: No timeline is currently open"

        # Get the specific clip or current clip
        if clip_name:
            # Find the clip by name in the timeline
            timeline_clips = current_timeline.GetItemListInTrack("video", 1)
            target_clip = None

            for clip in timeline_clips:
                if clip.GetName() == clip_name:
                    target_clip = clip
                    break

            if not target_clip:
                return f"Error: Clip '{clip_name}' not found in the timeline"

            # Select the clip
            current_timeline.SetCurrentSelectedItem(target_clip)

        # Get gallery
        gallery = current_project.GetGallery()
        if not gallery:
            return "Error: Failed to get gallery"

        # Get or create album
        album = None
        albums = gallery.GetAlbums()

        if albums:
            for a in albums:
                if a.GetName() == album_name:
                    album = a
                    break

        if not album:
            # Create a new album if it doesn't exist
            album = gallery.CreateAlbum(album_name)
            if not album:
                return f"Error: Failed to create album '{album_name}'"

        # Set preset name if specified
        final_preset_name = preset_name
        if not final_preset_name:
            if clip_name:
                final_preset_name = f"{clip_name} Preset"
            else:
                # Get current clip name if available
                current_clip = current_timeline.GetCurrentVideoItem()
                if current_clip:
                    final_preset_name = f"{current_clip.GetName()} Preset"
                else:
                    final_preset_name = f"Preset {len(album.GetStills()) + 1}"

        # Capture still
        result = gallery.GrabStill()

        if not result:
            return "Error: Failed to grab still for the preset"

        # Get the still that was just created
        stills = album.GetStills()
        if stills:
            latest_still = stills[-1]  # Assume the last one is the one we just grabbed
            # Set the label
            latest_still.SetLabel(final_preset_name)

        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)

        return f"Successfully saved color preset '{final_preset_name}' to album '{album_name}'"

    except Exception as e:
        # Return to the original page if we switched
        if current_page != "color":
            resolve.OpenPage(current_page)
        return f"Error saving color preset: {str(e)}"


@mcp.tool()
def save_layout_preset_tool(preset_name: str) -> Dict[str, Any]:
    """Save the current UI layout as a preset.

    Calls Resolve.SaveLayoutPreset() to save the current UI layout.

        Args:
        preset_name: Name for the saved preset.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.SaveLayoutPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


@mcp.tool()
def set_cache_path(path_type: str, path: str) -> str:
    """Set cache file path for the current project.

    Args:
    path_type: Type of cache path to set. Options: 'local', 'network'
    path: File system path for the cache
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    # Validate path_type
    valid_path_types = ["local", "network"]
    path_type = path_type.lower()
    if path_type not in valid_path_types:
        return f"Error: Invalid path type. Must be one of: {', '.join(valid_path_types)}"

    # Check if directory exists
    if not os.path.exists(path):
        return f"Error: Path '{path}' does not exist"

    setting_key = "LocalCachePath" if path_type == "local" else "NetworkCachePath"

    try:
        result = current_project.SetSetting(setting_key, path)
        if result:
            return f"Successfully set {path_type} cache path to '{path}'"
        else:
            return f"Failed to set {path_type} cache path to '{path}'"
    except Exception as e:
        return f"Error setting cache path: {str(e)}"


@mcp.tool()
def set_color_space_tool(color_space: str, gamma: str = None) -> str:
    """Set timeline color space and gamma.

    Args:
    color_space: Timeline color space (e.g., 'Rec.709', 'DCI-P3 D65', 'Rec.2020')
    gamma: Timeline gamma (e.g., 'Rec.709 Gamma', 'Gamma 2.4')
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    result = set_color_space(current_project, color_space, gamma)

    if result:
        if gamma:
            return f"Successfully set timeline color space to '{color_space}' with gamma '{gamma}'"
        else:
            return f"Successfully set timeline color space to '{color_space}'"
    else:
        return "Failed to set timeline color space"


@mcp.tool()
def set_color_wheel_param(wheel: str, param: str, value: float, node_index: int = None) -> str:
    """Set a color wheel parameter for a node.

    Args:
    wheel: Which color wheel to adjust ('lift', 'gamma', 'gain', 'offset')
    param: Which parameter to adjust ('red', 'green', 'blue', 'master')
    value: The value to set (typically between -1.0 and 1.0)
    node_index: Index of the node to set parameter for (uses current node if None)
    """
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def set_current_database(db_info: Dict[str, str]) -> Dict[str, Any]:
    """Switch to a different database.

    Args:
    db_info: Database info dict with keys 'DbType' and 'DbName'. Example: {"DbType": "Disk", "DbName": "Local Database"}
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    pm = resolve.GetProjectManager()
    result = pm.SetCurrentDatabase(db_info)
    return {"success": bool(result), "database": db_info}


@mcp.tool()
def set_current_render_format_and_codec(format_name: str, codec_name: str) -> Dict[str, Any]:
    """Set the render format and codec.

    Args:
    format_name: Render format (e.g. 'mp4', 'mov').
    codec_name: Codec name (e.g. 'H264', 'H265', 'ProRes422HQ').
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.SetCurrentRenderFormatAndCodec(format_name, codec_name)
    return {"success": bool(result), "format": format_name, "codec": codec_name}


@mcp.tool()
def set_current_render_mode(mode: int) -> Dict[str, Any]:
    """Set the render mode.

    Args:
    mode: 0 for Individual Clips, 1 for Single Clip.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    result = project.SetCurrentRenderMode(mode)
    return {"success": bool(result), "render_mode": mode}


@mcp.tool()
def set_gallery_album_name(name: str) -> Dict[str, Any]:
    """Set the name of the current gallery album.

    Args:
    name: New album name.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project open"}
    gallery = project.GetGallery()
    if not gallery:
        return {"error": "Failed to get Gallery"}
    result = gallery.SetAlbumName(name)
    return {"success": bool(result)}


@mcp.tool()
def set_high_priority() -> str:
    """Set the application to high priority mode."""
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    try:
        result = resolve.SetHighPriority()
        if result:
            return "Successfully set high priority mode"
        else:
            return "Failed to set high priority mode"
    except Exception as e:
        return f"Error setting high priority: {str(e)}"


@mcp.tool()
def set_keyframe_mode(mode: int) -> Dict[str, Any]:
    """Set the keyframe mode in Resolve.

    Args:
    mode: Keyframe mode - 0=All, 1=Color, 2=Sizing.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    if mode not in (0, 1, 2):
        return {"error": "Invalid mode. Must be 0 (All), 1 (Color), or 2 (Sizing)"}
    result = resolve.SetKeyframeMode(mode)
    mode_names = {0: "All", 1: "Color", 2: "Sizing"}
    return {
        "success": bool(result),
        "keyframe_mode": mode,
        "mode_name": mode_names[mode],
    }


@mcp.tool()
def set_voice_isolation_state(track_index: int = 1, state: str = None) -> str:
    """Set voice isolation state for a specific track.

    Args:
    track_index: The index of the track to set voice isolation state for (1-based index, defaults to 1)
    state: The voice isolation state to set
    """
    pm, current_project = get_current_project()
    if not current_project:
        return "Error: No project currently open"

    current_timeline = current_project.GetCurrentTimeline()
    if not current_timeline:
        return "Error: No timeline currently active"

    try:
        result = current_timeline.SetVoiceIsolationState(track_index, state)
        if result:
            return f"Successfully set voice isolation state to '{state}' for track {track_index}"
        else:
            return f"Failed to set voice isolation state for track {track_index}"
    except Exception as e:
        return f"Error setting voice isolation state: {str(e)}"


@mcp.tool()
def start_render() -> Dict[str, Any]:
    """Start rendering the jobs in the render queue."""
    return "Error: This function uses deprecated api/ module that has been removed. Use the compound server (server.py) instead."


@mcp.tool()
def stop_rendering() -> Dict[str, Any]:
    """Stop the current rendering process."""
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    project = resolve.GetProjectManager().GetCurrentProject()
    if not project:
        return {"error": "No project currently open"}
    project.StopRendering()
    return {"success": True}


@mcp.tool()
def switch_page(page: str) -> str:
    """Switch to a specific page in DaVinci Resolve.

    Args:
    page: The page to switch to. Options: 'media', 'cut', 'edit', 'fusion', 'color', 'fairlight', 'deliver'
    Valid: "edit", "cut", "color", "fusion", "fairlight", "deliver"
    """
    resolve = get_resolve()
    if resolve is None:
        return "Error: Not connected to DaVinci Resolve"

    valid_pages = ["media", "cut", "edit", "fusion", "color", "fairlight", "deliver"]
    page = page.lower()

    if page not in valid_pages:
        return f"Error: Invalid page name. Must be one of: {', '.join(valid_pages)}"

    result = resolve.OpenPage(page)
    if result:
        return f"Successfully switched to {page} page"
    else:
        return f"Failed to switch to {page} page"


@mcp.tool()
def ti_assign_to_color_group(
    group_name: str,
    item_index: int = 0,
    track_type: str = "video",
    track_index: int = 1,
) -> Dict[str, Any]:
    """Assign a timeline item to a color group.

    Args:
    group_name: Name of the color group.
    item_index: 0-based item index. Default: 0.
    """
    item, err = _get_timeline_item(track_type, track_index, item_index)
    if err:
        return err
    project = resolve.GetProjectManager().GetCurrentProject()
    groups = project.GetColorGroupsList()
    target = None
    if groups:
        for g in groups:
            if g.GetName() == group_name:
                target = g
                break
    if not target:
        return {"error": f"Color group '{group_name}' not found"}
    return {"success": bool(item.AssignToColorGroup(target))}


@mcp.tool()
def update_layout_preset(preset_name: str) -> Dict[str, Any]:
    """Overwrite an existing layout preset with the current UI layout.

    Args:
    preset_name: Name of the preset to overwrite.
    """
    resolve = get_resolve()
    if resolve is None:
        return {"error": "Not connected to DaVinci Resolve"}
    result = resolve.UpdateLayoutPreset(preset_name)
    return {"success": bool(result), "preset_name": preset_name}


# ── API Constants ─────────────────────────────────────────────────
ALL_CONSTANTS = {
    "composite_modes": [
        "Normal",
        "Add",
        "Subtract",
        "Multiply",
        "Screen",
        "Overlay",
        "Darken",
        "Lighten",
        "ColorDodge",
        "ColorBurn",
        "HardLight",
        "SoftLight",
        "Difference",
        "Exclusion",
        "Contrast",
        "Hue",
        "Saturation",
        "Color",
        "Luminosity",
        "Tile",
        "Behind",
        "Stencil",
        "OverlayStar",
        "Maximum",
    ],
    "retime_processes": ["Nearest", "FrameBlend", "FrameBlend Optical Flow", "Optical Flow"],
    "motion_estimation_modes": [
        "0=Medium",
        "1=Speed",
        "2=Quality",
        "3=Zero Latency",
        "4=Bidirectional",
        "5=Super High Quality",
        "6=User",
    ],
    "scaling_options": ["LockAspectRatio", "Fit", "Fill", "Stretch", "Crop"],
    "resize_filter_types": [
        "Nearest",
        "Box",
        "Bilinear",
        "Bicubic",
        "B-spline",
        "Lanczos",
        "Gauss",
        "Standard",
        "Bell",
        "Mitchell",
        "CubicSharp",
        "CubicSmooth",
        "CubicSharp2",
        "Disc",
        "Sinc",
        "Spline",
    ],
    "dynamic_zoom_ease": ["Linear", "EaseIn", "EaseOut", "EaseInOut"],
    "export_lut_types": ["Cubicle", "Flbox", "V ldap", ".3dl"],
    "export_types": [
        "AAF",
        "EDL",
        "FinalCut XML 7",
        "FinalCut XML 10",
        "Copy",
        "Move",
        "BWF",
        "Audio Only",
        "Video Only",
        "Auto",
        "Audio in Video",
        "CMX 3600",
        "Dictan",
        "Digies",
        "OMFI",
        "Text",
    ],
    "export_subtypes": ["None", "XML", "Copy", "Move", "BRAW", "R3D"],
    "audio_sync_settings": ["Off", "SceneDetect", "Timecode", "ClipChannel"],
    "auto_caption_models": ["Whisper"],
    "cache_settings": ["Auto", "On", "Off"],
    "keyframe_mode": ["Linear=0", "Bezier=1", "Constant=2"],
    "render_quality": [
        "Best",
        "Better",
        "Good",
        "Full",
        "Half",
        "Quarter",
        "Eighth",
        "Sixteenth",
        "Smooth",
        "Draft",
    ],
    "timeline_properties": [
        "Pan",
        "Tilt",
        "ZoomX",
        "ZoomY",
        "ZoomGang",
        "RotationAngle",
        "AnchorPointX",
        "AnchorPointY",
        "Pitch",
        "Yaw",
        "FlipX",
        "FlipY",
        "CropLeft",
        "CropRight",
        "CropTop",
        "CropBottom",
        "CropSoftness",
        "CropRetain",
        "DynamicZoomEase",
        "CompositeMode",
        "Opacity",
        "Distortion",
        "RetimeProcess",
        "MotionEstimation",
        "Scaling",
        "ResizeFilter",
    ],
    "color_group_return_types": ["PreColorGroup", "PostColorGroup"],
    "node_cache_settings": ["Auto", "On", "Off"],
    "fusion_cache_settings": ["Auto", "On", "Off"],
    "timeline_insert_ghost_clips": ["True", "False"],
    "import_destinations": ["Immediate", "Root", "SubFolder"],
}
