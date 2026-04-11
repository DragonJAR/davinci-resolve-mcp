# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.2.0] - 2026-04-10

### Added
- Modular granular server: 356 tools split into 10 focused modules
  - resolve_control, timeline, timeline_item, media_pool, media_pool_item
  - project, folder, gallery, graph, media_storage
- Enum documentation injected into 56 tool docstrings (Valid: lines in Args:)
- Parameter reference for AI agents (docs/PARAMETER_REFERENCE.md)
- CI pipeline with ruff lint + format + syntax checks
- Test suite with live API validation (93.3% coverage)
- ALL_CONSTANTS dictionary for resolve_constants tools

### Fixed
- All ruff lint errors from modularization (380 → 0)
- CI workflow YAML indentation (continue-on-error was nested inside run:)
- Missing utility imports in granular modules
- Bare except → except Exception across codebase
- project_manager → pm bug in close_project tool
- Missing current_timeline definition in export_all_powergrade_luts
- Missing ALL_CONSTANTS dictionary in resolve_control module

### Changed
- Ruff line-length increased to 220
- Ruff configured to ignore E402, F403, E501, N813 (structural rules for modularity)

## [2.1.0] - 2026-04-09

### Added
- pyproject.toml with ruff config, pytest, build metadata
- GitHub Actions CI (lint → test → import-check)
- Type hints across the codebase
- Cross-platform sandbox path redirects
- Auto-cleanup for grab_and_export function

### Fixed
- Repository references in package metadata
- Python path handling for DaVinci Resolve Modules

## [2.0.0] - 2026-04-08

### Added
- Initial public release
- 28 compound tools covering DaVinci Resolve Scripting API
- Interactive installer (python install.py) with auto-detection
- Support for Claude Desktop, Cursor, Windsurf, OpenCode, VS Code, Zed
- Cross-platform support: macOS, Windows, Linux
- External scripting configuration via Preferences > General
