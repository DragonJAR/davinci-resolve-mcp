# DaVinci Resolve MCP Server — Parameter Reference

Quick reference for AI agents using the granular MCP server (356 tools).

## Common Parameter Values

### Track Types
`"video"`, `"audio"`, `"subtitle"`

### Pages
`"edit"`, `"cut"`, `"color"`, `"fusion"`, `"fairlight"`, `"deliver"`

### Keyframe Modes
`0` = Linear, `1` = Bezier, `2` = Constant

### Composite Modes (19 values)
`Normal`, `Add`, `Subtract`, `Multiply`, `Screen`, `Overlay`, `Darken`, `Lighten`,
`ColorDodge`, `ColorBurn`, `LinearDodge`, `LinearBurn`, `HardLight`, `SoftLight`,
`PinLight`, `VividLight`, `Difference`, `Exclusion`, `Hue`

### Retime Process
`"nearest"` (0), `"frame_blend"` (2), `"optical_flow"` (3)

### Motion Estimation
`0` = project default, `1` = standard_faster, `2` = standard_better,
`3` = enhanced_faster, `4` = enhanced_better, `5` = enhanced_best, `6` = speed_warp_faster

### Keyframe Interpolation
`Linear`, `Bezier`, `EaseIn`, `EaseOut`, `EaseInOut`

### Marker Colors (16 values)
`Blue`, `Cyan`, `Green`, `Yellow`, `Red`, `Pink`, `Purple`, `Fuchsia`, `Rose`,
`Lavender`, `SkyBlue`, `Mint`, `Lemon`, `Sand`, `Cocoa`, `Cream`

### Cache Values
`"Auto"`, `"On"`, `"Off"`

### Grade Modes
`0` = No keyframes (default), `1` = Source Timecode aligned, `2` = Start Frames aligned

### Still Export Formats
`"dpx"`, `"cin"`, `"tif"`, `"jpg"`, `"png"`, `"ppm"`, `"bmp"`, `"xpm"`, `"drx"`

### Version Types
`0` = local, `1` = remote

### Magic Mask Modes
`"F"` = forward, `"B"` = backward, `"BI"` = bidirectional

### Fusion Tool Types (18 common)
`Merge`, `Background`, `TextPlus`, `Transform`, `Blur`, `ColorCorrector`,
`RectangleMask`, `EllipseMask`, `Tracker`, `MediaIn`, `MediaOut`, `Loader`, `Saver`,
`Glow`, `FilmGrain`, `CornerPositioner`, `DeltaKeyer`, `UltraKeyer`

## Common Parameter Structures

### CDL (Color Decision List)
```json
{"NodeIndex": 1, "Slope": [1.0, 1.0, 1.0], "Offset": [0.0, 0.0, 0.0], "Power": [1.0, 1.0, 1.0], "Saturation": 1.0}
```

### Graph Source
- `"timeline"` (default) — timeline node graph
- `"item"` — needs track_type, track_index, item_index
- `"color_group_pre"` / `"color_group_post"` — needs group_name

### Crop Values
All crop parameters: float `0.0` to `1.0`. `CropRetain`: boolean.

### Clip IDs
`clip_ids`: list of timeline item unique ID strings (obtained from `get_items_in_track` or similar)

### Folder Path
`folder_path`: absolute path to directory

### Album Index
`album_index`: 0-based index into still albums list

## Prerequisites by Tool Category

| Category | Prerequisite |
|----------|-------------|
| Project tools | Project must be open |
| Timeline tools | Timeline must be current |
| Timeline item tools | Items must exist on track (use `get_items_in_track` first) |
| Color tools | Works best on Color page |
| Gallery grab | Requires Color page active |
| Fusion comp | Requires a Fusion composition on the item |
| Render | Requires render jobs in queue |
