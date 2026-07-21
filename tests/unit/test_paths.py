"""Project path resolution tests."""

from __future__ import annotations

from pathlib import Path

from powerinsight.config import load_settings
from powerinsight.paths import PROJECT_ROOT, ProjectPaths, display_path


def test_paths_do_not_depend_on_current_working_directory(
    tmp_path: Path, monkeypatch: object
) -> None:
    monkeypatch.chdir(tmp_path)  # type: ignore[attr-defined]
    settings = load_settings(environment={})
    paths = ProjectPaths.from_settings(settings)

    assert paths.root == PROJECT_ROOT
    assert paths.builtin_csv == PROJECT_ROOT / "docs" / "household_power_consumption.csv"
    assert paths.data_dir == PROJECT_ROOT / "data"
    assert display_path(paths.builtin_csv) == "docs/household_power_consumption.csv"


def test_runtime_directories_are_created_under_configured_root(tmp_path: Path) -> None:
    settings = load_settings(
        environment={},
        runtime_overrides={
            "APP_DATA_DIR": "runtime-data",
            "APP_ARTIFACT_DIR": "runtime-artifacts",
            "APP_DATABASE_PATH": "runtime-artifacts/test.db",
        },
    )
    paths = ProjectPaths.from_settings(settings, root=tmp_path)
    paths.ensure_runtime_directories()

    assert paths.data_dir.is_dir()
    assert paths.artifact_dir.is_dir()
    assert paths.database_path.parent.is_dir()
    assert paths.log_dir.is_dir()
