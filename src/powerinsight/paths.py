"""Project-root-aware path resolution independent of the process working directory."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from powerinsight.config import AppSettings

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def resolve_project_path(value: str | Path, *, root: Path = PROJECT_ROOT) -> Path:
    """Resolve a configured path against the project root when it is relative."""
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def display_path(path: Path, *, root: Path = PROJECT_ROOT) -> str:
    """Return a project-relative path without leaking unrelated absolute directories."""
    resolved = path.resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError:
        return f"external:{resolved.name}"


@dataclass(frozen=True)
class ProjectPaths:
    """Resolved project paths used by infrastructure adapters."""

    root: Path
    data_dir: Path
    artifact_dir: Path
    database_path: Path
    log_dir: Path
    builtin_csv: Path

    @classmethod
    def from_settings(cls, settings: AppSettings, *, root: Path = PROJECT_ROOT) -> ProjectPaths:
        """Create paths from validated settings without using the current directory."""
        return cls(
            root=root.resolve(),
            data_dir=resolve_project_path(settings.app_data_dir, root=root),
            artifact_dir=resolve_project_path(settings.app_artifact_dir, root=root),
            database_path=resolve_project_path(settings.app_database_path, root=root),
            log_dir=(root / "logs").resolve(),
            builtin_csv=resolve_project_path(settings.data.builtin_path, root=root),
        )

    @property
    def writable_directories(self) -> tuple[Path, ...]:
        """Directories that the application must be able to create and write."""
        directories = (
            self.data_dir,
            self.data_dir / "raw",
            self.data_dir / "interim",
            self.data_dir / "processed",
            self.data_dir / "manifests",
            self.artifact_dir,
            self.artifact_dir / "forecasts",
            self.artifact_dir / "reports",
            self.artifact_dir / "figures",
            self.artifact_dir / "exports",
            self.artifact_dir / "demo",
            self.database_path.parent,
            self.log_dir,
        )
        return tuple(dict.fromkeys(directories))

    def ensure_runtime_directories(self) -> None:
        """Create only the writable directories needed by the current application skeleton."""
        for directory in self.writable_directories:
            directory.mkdir(parents=True, exist_ok=True)
