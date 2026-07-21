"""Application service for the complete built-in M2 data workflow."""

from __future__ import annotations

import time
from dataclasses import dataclass

import pandas as pd  # type: ignore[import-untyped]

from powerinsight.data import (
    BUILTIN_CSV_SHA256,
    ValidationResult,
    config_from_settings,
    preprocess_dataset,
    validate_csv,
)
from powerinsight.data.catalog import build_dataset_id, compute_sha256
from powerinsight.data.manifest import write_preprocess_artifacts
from powerinsight.data.preprocessing import build_preprocess_id, config_fingerprint
from powerinsight.paths import display_path
from powerinsight.persistence.metadata import (
    complete_preprocess_run,
    fail_preprocess_run,
    register_dataset,
    start_preprocess_run,
)
from powerinsight.schemas import DatasetManifest, ProcessedDatasetRecord
from powerinsight.services.runtime import RuntimeContext


@dataclass(frozen=True)
class BuiltinDataState:
    """Cheap current state used by home and data-center pages."""

    source_exists: bool
    source_path_alias: str
    sha256: str | None
    dataset_id: str | None
    manifest_path_alias: str | None
    manifest: DatasetManifest | None
    processed_exists: bool
    error: str | None = None


@dataclass(frozen=True)
class PipelineTimings:
    """Measured wall-clock durations for the M2 acceptance report."""

    validation_seconds: float
    preprocessing_write_seconds: float
    parquet_read_seconds: float


@dataclass(frozen=True)
class DataPipelineResult:
    """Completed source validation, artifacts, and measured timings."""

    validation: ValidationResult
    processed: ProcessedDatasetRecord
    manifest: DatasetManifest
    timings: PipelineTimings


class DataService:
    """Coordinate data domain functions, files, and metadata persistence."""

    def __init__(
        self,
        context: RuntimeContext,
        *,
        expected_sha256: str | None = BUILTIN_CSV_SHA256,
    ) -> None:
        self._context = context
        self._expected_sha256 = expected_sha256

    def inspect_builtin_state(self) -> BuiltinDataState:
        """Inspect identity and existing manifest without parsing the complete CSV."""
        path = self._context.paths.builtin_csv
        alias = display_path(path, root=self._context.paths.root)
        if not path.is_file():
            return BuiltinDataState(False, alias, None, None, None, None, False)
        try:
            sha256 = compute_sha256(path)
            dataset_id = build_dataset_id(alias, sha256)
            manifest_path = self._context.paths.data_dir / "manifests" / f"{dataset_id}.json"
            manifest_alias = display_path(manifest_path, root=self._context.paths.root)
            if not manifest_path.is_file():
                return BuiltinDataState(
                    True,
                    alias,
                    sha256,
                    dataset_id,
                    manifest_alias,
                    None,
                    False,
                )
            manifest = DatasetManifest.model_validate_json(
                manifest_path.read_text(encoding="utf-8")
            )
            if manifest.source_sha256 != sha256:
                return BuiltinDataState(
                    True,
                    alias,
                    sha256,
                    dataset_id,
                    manifest_alias,
                    None,
                    False,
                    "manifest 与当前原始文件指纹不一致",
                )
            processed_path = (
                self._context.paths.data_dir
                / "processed"
                / manifest.preprocess_id
                / "power_15min.parquet"
            )
            return BuiltinDataState(
                True,
                alias,
                sha256,
                dataset_id,
                manifest_alias,
                manifest,
                processed_path.is_file(),
            )
        except (OSError, ValueError) as exc:
            return BuiltinDataState(True, alias, None, None, None, None, False, str(exc))

    def validate_builtin(self, *, register: bool = True) -> ValidationResult:
        """Run full source validation and optionally register its lightweight metadata."""
        path = self._context.paths.builtin_csv
        result = validate_csv(
            path,
            path_alias=display_path(path, root=self._context.paths.root),
            expected_sha256=self._expected_sha256,
            raw_cadence=self._context.settings.data.raw_cadence,
            short_gap_max_minutes=self._context.settings.data.short_gap_max_minutes,
        )
        if register:
            register_dataset(self._context.paths.database_path, result.dataset, result.report)
        return result

    def prepare_builtin(self) -> DataPipelineResult:
        """Validate, process, write, reread, and register the built-in dataset."""
        validation_started = time.perf_counter()
        validation = self.validate_builtin(register=True)
        validation_seconds = time.perf_counter() - validation_started
        config = config_from_settings(self._context.settings.data)
        config_hash = config_fingerprint(config)
        preprocess_id = build_preprocess_id(validation.dataset.dataset_id, config_hash)
        data_alias = display_path(self._context.paths.data_dir, root=self._context.paths.root)
        processed_alias = f"{data_alias}/processed/{preprocess_id}/power_15min.parquet"
        start_preprocess_run(
            self._context.paths.database_path,
            preprocess_id=preprocess_id,
            dataset_id=validation.dataset.dataset_id,
            config_hash=config_hash,
            output_path_alias=processed_alias,
        )
        try:
            preprocessing_started = time.perf_counter()
            preprocess_result = preprocess_dataset(validation, config)
            processed, manifest = write_preprocess_artifacts(
                validation,
                preprocess_result,
                config,
                data_dir=self._context.paths.data_dir,
                data_dir_alias=data_alias,
            )
            preprocessing_seconds = time.perf_counter() - preprocessing_started
            processed_path = (
                self._context.paths.data_dir
                / "processed"
                / processed.preprocess_id
                / "power_15min.parquet"
            )
            read_started = time.perf_counter()
            reread_rows = len(pd.read_parquet(processed_path))
            parquet_read_seconds = time.perf_counter() - read_started
            if reread_rows != processed.processed_rows:
                raise ValueError("processed Parquet row count changed after writing")
            timings = PipelineTimings(
                validation_seconds=validation_seconds,
                preprocessing_write_seconds=preprocessing_seconds,
                parquet_read_seconds=parquet_read_seconds,
            )
            summary = {
                "minute_rows": processed.minute_rows,
                "processed_rows": processed.processed_rows,
                "split_counts": processed.split_counts,
                "imputed_rows": preprocess_result.imputed_row_count,
                "long_gap_rows": preprocess_result.long_gap_row_count,
                "negative_unmetered_rows": preprocess_result.negative_unmetered_count,
                "timings": {
                    "validation_seconds": validation_seconds,
                    "preprocessing_write_seconds": preprocessing_seconds,
                    "parquet_read_seconds": parquet_read_seconds,
                },
            }
            complete_preprocess_run(
                self._context.paths.database_path,
                processed,
                summary=summary,
            )
            return DataPipelineResult(validation, processed, manifest, timings)
        except Exception as exc:
            fail_preprocess_run(
                self._context.paths.database_path,
                preprocess_id=preprocess_id,
                error_code="PREP_PIPELINE_FAILED",
                message=str(exc).replace(str(self._context.paths.root), "."),
            )
            raise

    def load_processed_preview(self, manifest: DatasetManifest, *, rows: int = 20) -> pd.DataFrame:
        """Read only a small processed preview for UI display."""
        path = (
            self._context.paths.data_dir
            / "processed"
            / manifest.preprocess_id
            / "power_15min.parquet"
        )
        return pd.read_parquet(path).head(rows)
