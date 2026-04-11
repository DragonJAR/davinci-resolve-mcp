# Contributing to DaVinci Resolve MCP Server

Thank you for your interest in contributing! This document provides guidelines and instructions for contributing to this project.

## Code of Conduct

By participating in this project, you agree to maintain a respectful and constructive environment for everyone.

## Getting Started

### Prerequisites

- **DaVinci Resolve Studio 18.5+** with "External scripting" enabled in Preferences
- **Python 3.10-3.12**
- **Git** for version control

### Development Setup

```bash
# Clone the repository
git clone https://github.com/DragonJAR/davinci-resolve-mcp.git
cd davinci-resolve-mcp

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"

# Run linting
ruff check src/ install.py
ruff format --check src/ install.py
```

## Project Structure

```
davinci-resolve-mcp/
├── src/
│   ├── server.py              # Compound server (28 tools)
│   ├── granular/              # Modular server (356 tools in 10 modules)
│   │   ├── resolve_control.py # App control, presets, constants
│   │   ├── timeline.py       # Timeline management
│   │   ├── timeline_item.py  # Clip operations, keyframes, transforms
│   │   ├── media_pool.py    # Media pool management
│   │   ├── media_pool_item.py # Clip metadata and operations
│   │   ├── project.py        # Project management
│   │   ├── folder.py        # Folder navigation
│   │   ├── gallery.py        # Stills, albums, PowerGrade
│   │   ├── graph.py         # Color node graph
│   │   └── media_storage.py  # Storage browsing
│   └── utils/                # Shared utilities
│       ├── object_inspection.py
│       ├── layout_presets.py
│       ├── app_control.py
│       ├── cloud_operations.py
│       ├── project_properties.py
│       └── platform.py
├── examples/                  # Usage examples (validated against Resolve 20.3.2.9)
├── docs/                     # Documentation
├── tests/                    # Test suite
└── scripts/                  # Utility scripts
```

## Coding Standards

### Python Style

- Follow **PEP 8** guidelines
- Use **type hints** for all function parameters and return values
- Maximum line length: **220 characters** (configured in pyproject.toml)

### Ruff Linting

This project uses **ruff** for linting. All code must pass:

```bash
ruff check src/ install.py
ruff format --check src/ install.py
```

### Docstrings

All MCP tools must have docstrings following this format:

```python
@mcp.tool()
def my_tool(param1: str, param2: int = 10) -> Dict[str, Any]:
    """Short description of what the tool does.

    Longer description if needed, explaining the purpose
    and behavior of the tool.

    Args:
        param1: Description of param1.
        param2: Description of param2. Default: 10.

    Returns:
        Dictionary with the results.
    """
```

### Git Commit Messages

Use **Conventional Commits** format:

```
<type>(<scope>): <description>

[optional body]

[optional footer]
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

Examples:
```
feat(timeline): add scene detection tool
fix(media_pool): resolve import path issue
docs(readme): update API coverage badges
```

## Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src
```

### Writing Tests

- Place tests in `tests/` directory
- Use descriptive test names: `test_<function>_<scenario>_<expected>`
- Mock DaVinci Resolve API when possible (tests require Resolve to be running)

## Adding New Tools

### Guidelines

1. **One tool per concern** - Each tool should do one thing well
2. **Use existing helpers** - Don't duplicate utility functions
3. **Error handling** - Return error dictionaries, don't raise exceptions
4. **Validate inputs** - Check parameters before using them
5. **Document enums** - Use `Valid:` in docstrings for parameter options

### Module Organization

New tools should be added to the appropriate module:

| Module | Purpose |
|--------|---------|
| `resolve_control.py` | App-level operations, presets, constants |
| `timeline.py` | Timeline management, tracks, markers |
| `timeline_item.py` | Clip operations, transforms, keyframes |
| `media_pool.py` | Media pool organization |
| `media_pool_item.py` | Individual clip operations |
| `project.py` | Project management, cloud operations |
| `folder.py` | Folder navigation |
| `gallery.py` | Stills, albums, PowerGrade |
| `graph.py` | Color node graph |
| `media_storage.py` | Storage browsing |

## Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/my-feature`
3. **Make your changes** following the coding standards
4. **Run linting**: `ruff check src/ install.py && ruff format --check src/ install.py`
5. **Commit** using Conventional Commits
6. **Push** to your fork
7. **Open a Pull Request** against `main`

### PR Description

Include:
- Brief description of changes
- Related issue number (if applicable)
- Testing performed
- Screenshots/recordings for UI changes

## Reporting Issues

### Bug Reports

Include:
- DaVinci Resolve version
- MCP server version
- Steps to reproduce
- Expected vs actual behavior
- Error messages or logs

### Feature Requests

Include:
- Use case / motivation
- Proposed solution
- Alternatives considered

## Documentation

Update documentation when:
- Adding new tools or parameters
- Changing existing functionality
- Adding new examples
- Modifying the API

## Questions?

- Open an issue for bugs or feature requests
- Check existing issues before creating new ones

---

Last updated: 2026-04-10
