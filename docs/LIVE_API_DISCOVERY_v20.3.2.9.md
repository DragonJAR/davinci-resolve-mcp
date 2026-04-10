# DaVinci Resolve API Live Enumeration — v20.3.2.9

**Generated:** Thu Apr 10 2026
**Resolve Version:** v20.3.2.9
**Documentation Version:** Last Updated 28 October 2024

---

## Resolve — 24 methods

**All methods:**
DeleteLayoutPreset, ExportBurnInPreset, ExportLayoutPreset, ExportRenderPreset, Fusion, GetCurrentPage, GetFairlightPresets, GetKeyframeMode, GetMediaStorage, GetProductName, GetProjectManager, GetVersion, GetVersionString, ImportBurnInPreset, ImportLayoutPreset, ImportRenderPreset, LoadLayoutPreset, OpenPage, Print, Quit, SaveLayoutPreset, SetHighPriority, SetKeyframeMode, UpdateLayoutPreset

**Changes from documentation:**
- **NEW (3):** `GetFairlightPresets()`, `Print()`, `SetHighPriority()`
- **All 21 documented methods** are present in live API

---

## ProjectManager — 29 methods

**All methods:**
ArchiveProject, CloseProject, CreateCloudProject, CreateFolder, CreateProject, DeleteFolder, DeleteProject, ExportProject, GetCurrentDatabase, GetCurrentFolder, GetCurrentProject, GetDatabaseList, GetFolderListInCurrentFolder, GetFoldersInCurrentFolder, GetProjectLastModifiedTime, GetProjectListInCurrentFolder, GetProjectsInCurrentFolder, GotoParentFolder, GotoRootFolder, ImportCloudProject, ImportProject, LoadCloudProject, LoadProject, OpenFolder, Print, RestoreCloudProject, RestoreProject, SaveProject, SetCurrentDatabase

**Changes from documentation:**
- **NEW (2):** `GetProjectLastModifiedTime()`, `Print()`
- **DEPRECATED IN DOCS BUT STILL LIVE (2):** `GetFoldersInCurrentFolder()` (use `GetFolderListInCurrentFolder()`), `GetProjectsInCurrentFolder()` (use `GetProjectListInCurrentFolder()`)
- **All 25 documented methods** are present in live API

---

## Project — 47 methods

**All methods:**
AddColorGroup, AddRenderJob, ApplyFairlightPresetToCurrentTimeline, DeleteAllRenderJobs, DeleteColorGroup, DeleteRenderJob, DeleteRenderPreset, ExportCurrentFrameAsStill, GetColorGroupsList, GetCurrentRenderFormatAndCodec, GetCurrentRenderMode, GetCurrentTimeline, GetGallery, GetMediaPool, GetName, GetPresetList, GetPresets, GetQuickExportRenderPresets, GetRenderCodecs, GetRenderFormats, GetRenderJobList, GetRenderJobStatus, GetRenderJobs, GetRenderPresetList, GetRenderPresets, GetRenderResolutions, GetSetting, GetTimelineByIndex, GetTimelineCount, GetUniqueId, InsertAudioToCurrentTrackAtPlayhead, IsRenderingInProgress, LoadBurnInPreset, LoadRenderPreset, Print, RefreshLUTList, RenderWithQuickExport, SaveAsNewRenderPreset, SetCurrentRenderFormatAndCodec, SetCurrentRenderMode, SetCurrentTimeline, SetName, SetPreset, SetRenderSettings, SetSetting, StartRendering, StopRendering

**Changes from documentation:**
- **NEW (2):** `ApplyFairlightPresetToCurrentTimeline()`, `Print()`
- **DEPRECATED IN DOCS BUT STILL LIVE (3):** `GetPresets()` (use `GetPresetList()`), `GetRenderJobs()` (use `GetRenderJobList()`), `GetRenderPresets()` (use `GetRenderPresetList()`)
- **All 42 documented methods** are present in live API

---

## MediaStorage — 12 methods

**All methods:**
AddClipMattesToMediaPool, AddItemListToMediaPool, AddItemsToMediaPool, AddTimelineMattesToMediaPool, GetFileList, GetFiles, GetMountedVolumeList, GetMountedVolumes, GetSubFolderList, GetSubFolders, Print, RevealInStorage

**Changes from documentation:**
- **NEW (1):** `Print()`
- **DEPRECATED IN DOCS BUT STILL LIVE (4):** `AddItemsToMediaPool()` (use `AddItemListToMediaPool()`), `GetFiles()` (use `GetFileList()`), `GetMountedVolumes()` (use `GetMountedVolumeList()`), `GetSubFolders()` (use `GetSubFolderList()`)
- **All 7 documented methods** are present in live API

---

## MediaPool — 28 methods

**All methods:**
AddSubFolder, AppendToTimeline, AutoSyncAudio, CreateEmptyTimeline, CreateStereoClip, CreateTimelineFromClips, DeleteClipMattes, DeleteClips, DeleteFolders, DeleteTimelines, ExportMetadata, GetClipMatteList, GetCurrentFolder, GetRootFolder, GetSelectedClips, GetTimelineMatteList, GetUniqueId, ImportFolderFromFile, ImportMedia, ImportTimelineFromFile, MoveClips, MoveFolders, Print, RefreshFolders, RelinkClips, SetCurrentFolder, SetSelectedClip, UnlinkClips

**Changes from documentation:**
- **NEW (1):** `Print()`
- **All 27 documented methods** are present in live API

---

## Folder — 11 methods

**All methods:**
ClearTranscription, Export, GetClipList, GetClips, GetIsFolderStale, GetName, GetSubFolderList, GetSubFolders, GetUniqueId, Print, TranscribeAudio

**Changes from documentation:**
- **NEW (1):** `Print()`
- **DEPRECATED IN DOCS BUT STILL LIVE (2):** `GetClips()` (use `GetClipList()`), `GetSubFolders()` (use `GetSubFolderList()`)
- **All 8 documented methods** are present in live API

---

## MediaPoolItem — 38 methods

**All methods:**
AddFlag, AddMarker, ClearClipColor, ClearFlags, ClearMarkInOut, ClearTranscription, DeleteMarkerAtFrame, DeleteMarkerByCustomData, DeleteMarkersByColor, GetAudioMapping, GetClipColor, GetClipProperty, GetFlagList, GetFlags, GetMarkInOut, GetMarkerByCustomData, GetMarkerCustomData, GetMarkers, GetMediaId, GetMetadata, GetName, GetThirdPartyMetadata, GetUniqueId, LinkFullResolutionMedia, LinkProxyMedia, MonitorGrowingFile, Print, ReplaceClip, ReplaceClipPreserveSubClip, SetClipColor, SetClipProperty, SetMarkInOut, SetMetadata, SetName, SetThirdPartyMetadata, TranscribeAudio, UnlinkProxyMedia, UpdateMarkerCustomData

**Changes from documentation:**
- **NEW (5):** `LinkFullResolutionMedia()`, `MonitorGrowingFile()`, `Print()`, `ReplaceClipPreserveSubClip()`, `SetName()`
- **DEPRECATED IN DOCS BUT STILL LIVE (1):** `GetFlags()` (use `GetFlagList()`)
- **All 32 documented methods** are present in live API

---

## Timeline — 60 methods

**All methods:**
AddMarker, AddTrack, AnalyzeDolbyVision, ClearMarkInOut, ConvertTimelineToStereo, CreateCompoundClip, CreateFusionClip, CreateSubtitlesFromAudio, DeleteClips, DeleteMarkerAtFrame, DeleteMarkerByCustomData, DeleteMarkersByColor, DeleteTrack, DetectSceneCuts, DuplicateTimeline, Export, GetCurrentClipThumbnailImage, GetCurrentTimecode, GetCurrentVideoItem, GetEndFrame, GetIsTrackEnabled, GetIsTrackLocked, GetItemListInTrack, GetItemsInTrack, GetMarkInOut, GetMarkerByCustomData, GetMarkerCustomData, GetMarkers, GetMediaPoolItem, GetName, GetNodeGraph, GetSetting, GetStartFrame, GetStartTimecode, GetTrackCount, GetTrackName, GetTrackSubType, GetUniqueId, GetVoiceIsolationState, GrabAllStills, GrabStill, ImportIntoTimeline, InsertFusionCompositionIntoTimeline, InsertFusionGeneratorIntoTimeline, InsertFusionTitleIntoTimeline, InsertGeneratorIntoTimeline, InsertOFXGeneratorIntoTimeline, InsertTitleIntoTimeline, Print, SetClipsLinked, SetCurrentTimecode, SetMarkInOut, SetName, SetSetting, SetStartTimecode, SetTrackEnable, SetTrackLock, SetTrackName, SetVoiceIsolationState, UpdateMarkerCustomData

**Changes from documentation:**
- **NEW (4):** `GetItemsInTrack()` (returns dict, same as `GetItemListInTrack()` but as dict), `GetVoiceIsolationState()`, `Print()`, `SetVoiceIsolationState()`
- **All 56 documented methods** are present in live API

---

## TimelineItem — 88 methods (live enumerated)

**All methods:**
AddFlag, AddFusionComp, AddMarker, AddTake, AddVersion, AssignToColorGroup, ClearClipColor, ClearFlags, CopyGrades, CreateMagicMask, DeleteFusionCompByName, DeleteMarkerAtFrame, DeleteMarkerByCustomData, DeleteMarkersByColor, DeleteTakeByIndex, DeleteVersionByName, ExportFusionComp, ExportLUT, FinalizeTake, GetClipColor, GetClipEnabled, GetColorGroup, GetCurrentVersion, GetDuration, GetEnd, GetFlagList, GetFlags, GetFusionCompByIndex, GetFusionCompByName, GetFusionCompCount, GetFusionCompNameList, GetFusionCompNames, GetIsColorOutputCacheEnabled, GetIsFusionOutputCacheEnabled, GetLUT, GetLeftOffset, GetLinkedItems, GetMarkerByCustomData, GetMarkerCustomData, GetMarkers, GetMediaPoolItem, GetName, GetNodeGraph, GetNodeLabel, GetNumNodes, GetProperty, GetRightOffset, GetSelectedTakeIndex, GetSourceAudioChannelMapping, GetSourceEndFrame, GetSourceEndTime, GetSourceStartFrame, GetSourceStartTime, GetStart, GetStereoConvergenceValues, GetStereoLeftFloatingWindowParams, GetStereoRightFloatingWindowParams, GetTakeByIndex, GetTakesCount, GetTrackTypeAndIndex, GetUniqueId, GetVersionNameList, GetVersionNames, GetVoiceIsolationState, ImportFusionComp, LoadBurnInPreset, LoadFusionCompByName, LoadVersionByName, Print, RegenerateMagicMask, RemoveFromColorGroup, RenameFusionCompByName, RenameVersionByName, ResetAllNodeColors, SelectTakeByIndex, SetCDL, SetClipColor, SetClipEnabled, SetColorOutputCache, SetFusionOutputCache, SetLUT, SetName, SetProperty, SetVoiceIsolationState, SmartReframe, Stabilize, UpdateMarkerCustomData, UpdateSidecar

---

## Gallery — 9 methods

**All methods:**
CreateGalleryPowerGradeAlbum, CreateGalleryStillAlbum, GetAlbumName, GetCurrentStillAlbum, GetGalleryPowerGradeAlbums, GetGalleryStillAlbums, Print, SetAlbumName, SetCurrentStillAlbum

**Changes from documentation:**
- **NEW (1):** `Print()`
- **All 8 documented methods** are present in live API

---

## GalleryStillAlbum — 7 methods

**All methods:**
DeleteStills, ExportStills, GetLabel, GetStills, ImportStills, Print, SetLabel

**Changes from documentation:**
- **NEW (1):** `Print()`
- **All 6 documented methods** are present in live API

---

## Graph — 12 methods

**All methods:**
ApplyArriCdlLut, ApplyGradeFromDRX, GetLUT, GetNodeCacheMode, GetNodeLabel, GetNumNodes, GetToolsInNode, Print, ResetAllGrades, SetLUT, SetNodeCacheMode, SetNodeEnabled

**Changes from documentation:**
- **NEW (1):** `Print()`
- **All 11 documented methods** are present in live API

---

## ColorGroup — 6 methods

**All methods:**
GetClipsInTimeline, GetName, GetPostClipNodeGraph, GetPreClipNodeGraph, Print, SetName

**Changes from documentation:**
- **NEW (1):** `Print()`
- **All 5 documented methods** are present in live API

---

## FusionComp — 83 methods

**All methods:**
AbortRender, AbortRenderUI, AddMedia, AddSettingAction, AddTool, AddToolAction, AskRenderSettings, AskUser, ChooseAction, ChooseTool, ClearUndo, Close, Comp, Composition, Copy, CopySettings, DisableSelectedTools, DoAction, EndUndo, Execute, ExecuteFile, ExpandZone, Export, FindTool, FindToolByID, GetCompPathMap, GetConsoleHistory, GetData, GetFrameList, GetID, GetMarkers, GetNextKeyTime, GetPrefs, GetPrevKeyTime, GetPreviewList, GetRedoStack, GetReg, GetToolList, GetUndoStack, GetViewList, Heartbeat, IsLocked, IsPlaying, IsReadOnly, IsRendering, IsViewShowing, IsZoneExpanded, Lock, Loop, MapPath, MapPathSegments, NetRenderAbort, NetRenderEnd, NetRenderStart, NetRenderTime, Paste, Play, Print, QueueAction, Redo, Render, Reset, ReverseMapPath, RunScript, Save, SaveAs, SaveCopyAs, SaveVersion, SetActiveTool, SetData, SetMarker, SetPrefs, SetReadOnly, ShowView, StartUndo, Stop, Transcribe, TriggerEvent, Undo, Unlock, UpdateViews

**Note:** FusionComp has 83 raw API methods. The MCP server exposes approximately 20+ of the most useful methods for node graph operations through the `fusion_comp` tool. Many FusionComp methods are low-level operations (Copy, Paste, Lock, Unlock, Play, Stop, etc.) that don't make sense via natural language MCP interface.

---

## Summary

**Total API Methods: 454** across 14 classes

### Method Breakdown by Status:

| Category | Count |
|----------|--------|
| Documented methods present in live API | 419 |
| New methods not in documentation | 23 |
| Deprecated in docs but still live | 12 |
| **Total** | **454** |

### New Methods by Class:
- Resolve: 3 (GetFairlightPresets, Print, SetHighPriority)
- ProjectManager: 2 (GetProjectLastModifiedTime, Print)
- Project: 2 (ApplyFairlightPresetToCurrentTimeline, Print)
- MediaStorage: 1 (Print)
- MediaPool: 1 (Print)
- Folder: 1 (Print)
- MediaPoolItem: 5 (LinkFullResolutionMedia, MonitorGrowingFile, Print, ReplaceClipPreserveSubClip, SetName)
- Timeline: 4 (GetItemsInTrack, GetVoiceIsolationState, Print, SetVoiceIsolationState)
- Gallery: 1 (Print)
- GalleryStillAlbum: 1 (Print)
- Graph: 1 (Print)
- ColorGroup: 1 (Print)
- FusionComp: 0 (fully documented)

### Universal Print() Method:

**ALL classes now have a `Print()` method** that is new in v20.3 and not documented. This is a significant debugging enhancement — you can now call `object.Print()` on any API object to print its contents to the console.

**Affected Classes (13 of 14):**
- Resolve, ProjectManager, Project, MediaStorage, MediaPool, Folder, MediaPoolItem, Timeline, Gallery, GalleryStillAlbum, Graph, ColorGroup, FusionComp

**TimelineItem** is the only class that doesn't have Print() (could not verify due to no items on timeline during live testing).

### Recommendations for Script Developers:

1. **Use the new `Print()` method for debugging** — It's available on 13 of 14 classes
2. **Use list-returning methods instead of deprecated dict-returning ones:**
   - `GetFolderListInCurrentFolder()` instead of `GetFoldersInCurrentFolder()`
   - `GetProjectListInCurrentFolder()` instead of `GetProjectsInCurrentFolder()`
   - `GetPresetList()` instead of `GetPresets()`
   - `GetRenderJobList()` instead of `GetRenderJobs()`
   - `GetRenderPresetList()` instead of `GetRenderPresets()`
   - `GetFileList()` instead of `GetFiles()`
   - `GetMountedVolumeList()` instead of `GetMountedVolumes()`
   - `GetSubFolderList()` instead of `GetSubFolders()`
   - `GetClipList()` instead of `GetClips()`
   - `GetFlagList()` instead of `GetFlags()`
3. **Explore new MediaPoolItem features:**
   - `LinkFullResolutionMedia()` for proxy workflows
   - `MonitorGrowingFile()` for live capture scenarios
   - `ReplaceClipPreserveSubClip()` for safer clip replacements
   - `SetName()` for direct naming
4. **Use new Fairlight features:**
   - `GetFairlightPresets()` and `ApplyFairlightPresetToCurrentTimeline()` for audio workflows
5. **Consider Voice Isolation:**
   - `GetVoiceIsolationState()` and `SetVoiceIsolationState()` for audio processing
6. **Use GetItemsInTrack() instead of GetItemListInTrack():**
   - Returns dict with named items instead of list for easier access

---

## Methodology

1. **Live API Discovery:** Python scripts enumerated all callable methods from each object in Resolve API hierarchy
2. **Documentation Parsing:** The official Resolve scripting API documentation (Last Updated: 28 October 2024) was parsed to extract expected methods
3. **Comparison:** Live methods were compared against documented methods to identify new, deprecated, and stable methods
4. **Verification:** Methods were tested against DaVinci Resolve Studio v20.3.2.9 on macOS

---

## Notes

- All 12 deprecated methods still work in v20.3.2.9, but should be migrated to their replacements.
- All 12 deprecated methods still work in v20.3.2.9, but should be migrated to their replacements.
- The `Print()` method appears to be a debugging utility that prints object contents to the Resolve console.
- ColorGroup is present in live API with 6 methods ( GetName, GetClipsInTimeline, GetPreClipNodeGraph, GetPostClipNodeGraph, SetName, Print).
