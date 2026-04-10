# Modularization — COMPLETED

## What Was Done

The `resolve_mcp_server.py` monolith (10,081 lines, 356 tools) has been split into focused modules.

## Actual Structure

```
src/
├── server.py                     # Compound server (28 tools) — unchanged
├── resolve_mcp_server.py         # Thin entry point — imports granular package
├── granular/                    # Modular granular server
│   ├── __init__.py               # Creates mcp server, imports all modules
│   ├── resolve_control.py        # 100 tools — Resolve app-level operations
│   ├── project.py                # 28 tools — Project management
│   ├── timeline.py               # 61 tools — Timeline operations
│   ├── timeline_item.py          # 76 tools — Clip/item operations
│   ├── media_pool_item.py        # 45 tools — MediaPoolItem operations
│   ├── media_pool.py             # 17 tools — MediaPool operations
│   ├── folder.py                 # 12 tools — Folder operations
│   ├── gallery.py                # 9 tools — Gallery operations
│   ├── graph.py                  # 7 tools — Node graph operations
│   └── media_storage.py          # 1 tool — MediaStorage operations
└── utils/                       # Existing utils — unchanged
```

**Total: 356 tools across 10 modules** (vs 14 modules proposed — some categories merged)

## How It Works

1. `granular/__init__.py` creates the `FastMCP` server instance FIRST
2. Then imports all module files, which use `@mcp.tool()` to register tools
3. `resolve_mcp_server.py` is a thin entry point that:
   - Sets up the Resolve API path
   - Imports utility functions
   - Imports `from granular import mcp`
   - Runs `mcp.run()`

## Splitting Script

`scripts/split_granular.py` — idempotent script that can re-split from backup.

```bash
python3 scripts/split_granular.py --dry-run   # preview
python3 scripts/split_granular.py              # split
python3 scripts/split_granular.py --restore   # restore from backup
```

The script:
- Parses the monolithic file using AST (not regex)
- Extracts all 356 `@mcp.tool()` functions with their decorators
- Categorizes tools by most-used API variable (resolve, project, tl, item, etc.)
- Dedents helper functions for module-level placement
- Verifies syntax of every module before writing

## Module Sizes

| Module | Tools | Size |
|--------|-------|------|
| resolve_control | 100 | 117KB |
| timeline_item | 76 | 109KB |
| timeline | 61 | 72KB |
| media_pool_item | 45 | 72KB |
| project | 28 | 63KB |
| media_pool | 17 | 48KB |
| folder | 12 | 51KB |
| gallery | 9 | 47KB |
| graph | 7 | 44KB |
| media_storage | 1 | 41KB |

## Key Design Decisions

### Helpers in Every Module
Rather than a central `helpers.py`, each module includes the helpers it needs. This adds some duplication but avoids import complexity and keeps each module self-contained.

### MCP Server in __init__.py
`granular/__init__.py` creates the `mcp` server instance before importing submodules. This allows each submodule to use `@mcp.tool()` while `mcp` is in scope.

### Categorization Algorithm
Tools are categorized by which API variable they use most:
1. Count `resolve.`, `project.`, `tl.`, `item.`, `clip.`, `folder.`, `ms.`, `mp.`, `gallery.`, `graph.`, `cg.`, `fusion.` calls
2. Map the most-used variable to its API class
3. Name-based fallback for ambiguous cases

## Backward Compatibility

- All 356 original tool names preserved exactly
- All tool signatures (parameters, return types) unchanged
- The thin `resolve_mcp_server.py` can replace the old monolith
- MCP clients connecting to `resolve_mcp_server.py` work identically
