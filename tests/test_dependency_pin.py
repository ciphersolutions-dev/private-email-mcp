"""Unit regression: mcp SDK must stay on the FastMCP v1 line."""

from __future__ import annotations

import importlib.metadata
from pathlib import Path

import privateemail_mcp.server  # noqa: F401 — import crash is the regression


def test_pyproject_pins_mcp_below_v2():
    text = Path(__file__).resolve().parents[1] / "pyproject.toml"
    contents = text.read_text()
    assert "mcp[cli]>=1.6.0,<2.0.0" in contents


def test_installed_mcp_is_v1_with_fastmcp():
    version = importlib.metadata.version("mcp")
    assert int(version.split(".", 1)[0]) == 1
    from mcp.server.fastmcp import FastMCP

    assert FastMCP is not None


def test_package_metadata_exposes_upper_bound():
    reqs = importlib.metadata.requires("privateemail-mcp") or []
    mcp_reqs = [r for r in reqs if r.lower().startswith("mcp")]
    joined = " ".join(mcp_reqs)
    assert "<2" in joined or "<2.0" in joined
