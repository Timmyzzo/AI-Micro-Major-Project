"""Stable dataset identity and immutable source-file fingerprinting."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

BUILTIN_CSV_SHA256 = "C79E3E19348BF518748D63455F98B2F09DAF9B1A72FA3F42048FADD9A588225E"
DATA_SCHEMA_VERSION = "1.0"


def compute_sha256(path: Path) -> str:
    """Return the uppercase SHA-256 for a file without modifying it."""
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def build_dataset_id(path_alias: str, sha256: str) -> str:
    """Build a readable stable ID from a non-sensitive alias and source fingerprint."""
    alias_stem = Path(path_alias).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "_", alias_stem).strip("_")[:16].strip("_") or "dataset"
    return f"ds_{slug}_{sha256[:8].lower()}"
