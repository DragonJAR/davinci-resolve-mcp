"""Basic import and syntax validation tests."""

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent


def test_server_syntax():
    """Compound server parses without errors."""
    source = (PROJECT_ROOT / "src" / "server.py").read_text()
    assert ast.parse(source) is not None


def test_granular_server_syntax():
    """Granular server parses without errors."""
    source = (PROJECT_ROOT / "src" / "resolve_mcp_server.py").read_text()
    assert ast.parse(source) is not None


def test_install_syntax():
    """Installer parses without errors."""
    source = (PROJECT_ROOT / "install.py").read_text()
    assert ast.parse(source) is not None


def test_utils_syntax():
    """All utils parse without errors."""
    utils_dir = PROJECT_ROOT / "src" / "utils"
    for py_file in utils_dir.glob("*.py"):
        source = py_file.read_text()
        assert ast.parse(source) is not None, f"{py_file.name} has syntax errors"


def test_server_has_tools():
    """Compound server defines expected number of tools."""
    source = (PROJECT_ROOT / "src" / "server.py").read_text()
    tool_count = source.count("@mcp.tool()")
    assert tool_count == 28, f"Expected 28 tools, found {tool_count}"


def test_granular_server_has_tools():
    """Granular server defines expected number of tools."""
    source = (PROJECT_ROOT / "src" / "resolve_mcp_server.py").read_text()
    tool_count = source.count("@mcp.tool()")
    assert tool_count == 356, f"Expected 356 tools, found {tool_count}"


def test_pyproject_exists():
    """pyproject.toml exists and is valid."""
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.exists()
    content = pyproject.read_text()
    assert "davinci-resolve-mcp" in content
    assert "2.2.0" in content
