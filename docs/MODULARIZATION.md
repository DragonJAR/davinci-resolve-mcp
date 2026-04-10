# Modularization Plan

## Current State

`src/resolve_mcp_server.py` is a ~10,100 line monolith containing 356 tool registrations and their handlers.

## Proposed Structure

```
src/
├── server.py                 # Compound server (28 tools) — unchanged
├── resolve_mcp_server.py     # Thin entry point — imports and registers all modules
├── granular/                 # Modular granular server
│   ├── __init__.py           # Package init, registers all tools
│   ├── resolve_control.py    # Resolve app tools (~24 methods)
│   ├── project_manager.py    # ProjectManager tools (~29 methods)
│   ├── project.py            # Project tools (~47 methods)
│   ├── media_storage.py      # MediaStorage tools (~12 methods)
│   ├── media_pool.py         # MediaPool + Folder tools (~39 methods)
│   ├── media_pool_item.py    # MediaPoolItem tools (~38 methods)
│   ├── timeline.py           # Timeline tools (~60 methods)
│   ├── timeline_item.py      # TimelineItem tools (~76 methods) — largest module
│   ├── gallery.py            # Gallery + GalleryStillAlbum tools (~16 methods)
│   ├── graph.py              # Graph tools (~12 methods)
│   ├── color_group.py        # ColorGroup tools (~6 methods)
│   ├── fusion_comp.py        # FusionComp tools (~83 methods)
│   └── helpers.py            # Shared helpers, validation, constants
└── utils/                    # Existing utils — unchanged
```

## Migration Steps

1. Extract helpers and shared validation into `granular/helpers.py`
2. Move each class's tool registrations into its own module
3. Keep `resolve_mcp_server.py` as thin entry point
4. Maintain backward compatibility — same 356 tools, same behavior

## Benefits

- Each module 300-800 lines (manageable)
- Easier to test individual components
- Easier to contribute (focused PRs)
- Better code organization

## Risks

- Breaking existing MCP client configs referencing resolve_mcp_server.py
- Must preserve exact tool names and behavior
