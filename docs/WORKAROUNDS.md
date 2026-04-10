# API Workarounds

Common editor operations NOT directly supported by DaVinci Resolve Scripting API and suggested workarounds.

| Operation | Status | Workaround |
|-----------|--------|------------|
| **Blade/Split clip** | ❌ Not available | No `BladeClip()` method. Delete and re-import clips as workaround. |
| **Insert at playhead** | ❌ Not available | Use `timeline_item.set_property()` to adjust clip boundaries. |
| **Ripple delete** | ⚠️ Partial | `timeline.DeleteClips(clip_ids, ripple=True)` — unconfirmed behavior. |
| **Nudge clip (move frames)** | ❌ Not available | Use `get_left_offset()` + `set_property()` to adjust position. |
| **Copy/Paste attributes** | ❌ Not available | Read source with `get_property()`, apply to target with `set_property()`. |
| **Audio waveform display** | ❌ Not available | No API control for waveform visibility. |
| **Set playhead position** | ✅ Available | `timeline.SetCurrentTimecode("01:00:00:00")` |
| **Keyboard shortcuts** | ❌ Not available | Resolve API does not expose keyboard shortcut simulation. |
