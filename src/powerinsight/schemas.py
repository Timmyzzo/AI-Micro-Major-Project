"""Shared domain schemas for the PowerInsight application."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

IssueSeverity = Literal["error", "warning", "information"]
QualityStatus = Literal["usable", "attention", "blocked"]
DatasetStatus = Literal["registered", "validated", "invalid"]
RunStatus = Literal["running", "completed", "failed"]


class SystemStatus(BaseModel):
    """Non-sensitive runtime status rendered by the home and settings pages."""

    model_config = ConfigDict(frozen=True)

    python_version: str
    torch_version: str
    cuda_runtime: str | None
    cuda_available: bool
    gpu_name: str | None
    gpu_memory_bytes: int | None
    config_sources: tuple[str, ...]
    data_file_exists: bool
    data_status: str
    model_status: str
    database_accessible: bool
    database_status: str
    llm_enabled: bool
    llm_configured: bool
    llm_status: str


class DataIssue(BaseModel):
    """One deterministic validation finding with an actionable remediation."""

    model_config = ConfigDict(frozen=True)

    code: str
    severity: IssueSeverity
    message: str
    count: int = Field(default=1, ge=1)
    start_time: datetime | None = None
    end_time: datetime | None = None
    suggested_action: str


class MissingBlock(BaseModel):
    """One consecutive block of rows containing missing measurements."""

    model_config = ConfigDict(frozen=True)

    start_time: datetime
    end_time: datetime
    length_minutes: int = Field(ge=1)
    missing_columns: tuple[str, ...]


class DatasetRecord(BaseModel):
    """Stable identity and verified metadata for one source dataset."""

    model_config = ConfigDict(frozen=True)

    schema_version: str
    dataset_id: str
    name: str
    source_type: Literal["built_in", "upload"]
    path_alias: str
    sha256: str
    size_bytes: int = Field(ge=0)
    row_count: int = Field(ge=0)
    field_count: int = Field(ge=0)
    start_time: datetime | None = None
    end_time: datetime | None = None
    cadence: str | None = None
    status: DatasetStatus
    created_at: datetime


class DataQualityReport(BaseModel):
    """Serializable data-quality result used by scripts, storage, and UI."""

    model_config = ConfigDict(frozen=True)

    dataset_id: str
    validation_version: str
    status: QualityStatus
    score: float | None = Field(default=None, ge=0.0, le=100.0)
    row_count: int = Field(ge=0)
    parsed_timestamp_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    cadence_violations: int = Field(ge=0)
    missing_cells_by_column: dict[str, int]
    measurement_missing_row_count: int = Field(ge=0)
    missing_blocks: tuple[MissingBlock, ...]
    issues: tuple[DataIssue, ...]
    generated_at: datetime

    def issue_count(self, severity: IssueSeverity) -> int:
        """Return the number of findings at one severity level."""
        return sum(issue.severity == severity for issue in self.issues)


class PreprocessConfig(BaseModel):
    """All deterministic rules that influence an M2 processed dataset."""

    model_config = ConfigDict(frozen=True)

    schema_version: str = "1.0"
    raw_cadence: str = "1min"
    target_cadence: str = "15min"
    short_gap_max_minutes: int = Field(default=60, ge=0)
    bucket_min_valid_ratio: float = Field(default=0.8, gt=0.0, le=1.0)
    unmetered_negative_tolerance_wh: float = Field(default=1e-9, ge=0.0)
    train_end: datetime
    validation_end: datetime
    test_end: datetime

    @model_validator(mode="after")
    def validate_split_boundaries(self) -> PreprocessConfig:
        """Require strictly increasing fixed time split boundaries."""
        if not self.train_end < self.validation_end < self.test_end:
            raise ValueError("split boundaries must be strictly increasing")
        return self


class ProcessedDatasetRecord(BaseModel):
    """Metadata for one repeatable preprocessing result."""

    model_config = ConfigDict(frozen=True)

    schema_version: str
    preprocess_id: str
    dataset_id: str
    config_hash: str
    minute_path_alias: str
    processed_path_alias: str
    manifest_path_alias: str
    minute_rows: int = Field(ge=0)
    processed_rows: int = Field(ge=0)
    split_counts: dict[str, int]
    status: RunStatus
    created_at: datetime


class DatasetManifest(BaseModel):
    """Complete, non-sensitive provenance for an M2 preprocessing artifact."""

    model_config = ConfigDict(frozen=True)

    schema_version: str
    dataset_id: str
    preprocess_id: str
    config_hash: str
    source_path_alias: str
    source_sha256: str
    source_rows: int = Field(ge=0)
    source_fields: int = Field(ge=0)
    start_time: datetime
    end_time: datetime
    cadence: dict[str, str]
    columns: dict[str, dict[str, str]]
    missing_summary: dict[str, object]
    preprocessing: dict[str, object]
    splits: dict[str, object]
    artifacts: dict[str, str]
    quality_report: DataQualityReport
    created_at: datetime
    software_versions: dict[str, str]
