"""Installed package and immutable raw-data contract tests."""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path

import pytest
from transformers import PatchTSTConfig

from powerinsight import __version__
from powerinsight.paths import PROJECT_ROOT

EXPECTED_CSV_SHA256 = "C79E3E19348BF518748D63455F98B2F09DAF9B1A72FA3F42048FADD9A588225E"


@pytest.mark.parametrize(
    "module_name",
    (
        "joblib",
        "numpy",
        "openai",
        "pandas",
        "plotly",
        "pyarrow",
        "pydantic",
        "pydantic_settings",
        "scipy",
        "sklearn",
        "streamlit",
        "torch",
        "transformers",
        "yaml",
    ),
)
def test_required_runtime_dependency_imports(module_name: str) -> None:
    assert importlib.import_module(module_name) is not None


def test_project_package_and_patchtst_contract_import() -> None:
    assert __version__ == "0.1.0"
    assert PatchTSTConfig.__name__ == "PatchTSTConfig"


def test_raw_csv_exists_and_sha256_is_unchanged() -> None:
    csv_path = PROJECT_ROOT / "docs" / "household_power_consumption.csv"

    assert csv_path.is_file()
    assert _sha256(csv_path) == EXPECTED_CSV_SHA256


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()
