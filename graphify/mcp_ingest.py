"""Stub for mcp_ingest — satisfies import in extract.py."""
from pathlib import Path


def is_mcp_config_path(path: Path) -> bool:
    return False


def extract_mcp_config(path: Path) -> dict:
    return {"nodes": [], "edges": []}
