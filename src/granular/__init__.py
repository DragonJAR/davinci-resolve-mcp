#!/usr/bin/env python3
"""Granular DaVinci Resolve MCP Server — modular package."""

import logging

# ── Create MCP server (MUST be defined before modules import it) ────
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("davinci-resolve-granular")

# ── Import all tool modules (they use the mcp instance above) ───────
from granular.folder import *
from granular.gallery import *
from granular.graph import *
from granular.media_pool import *
from granular.media_pool_item import *
from granular.media_storage import *
from granular.project import *
from granular.timeline import *
from granular.timeline_item import *

logger = logging.getLogger(__name__)
