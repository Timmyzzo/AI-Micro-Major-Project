"""Full CSV M2 preprocessing and repeatable artifact integration test."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from powerinsight.config import load_settings
from powerinsight.data import (
    BUILTIN_CSV_SHA256,
    config_from_settings,
    preprocess_dataset,
    validate_csv,
)
from powerinsight.data.manifest import write_preprocess_artifacts
from powerinsight.paths import PROJECT_ROOT


def test_builtin_csv_preprocessing_and_artifacts_are_consistent(tmp_path: Path) -> None:
    settings = load_settings(environment={})
    config = config_from_settings(settings.data)
    path = PROJECT_ROOT / "docs" / "household_power_consumption.csv"
    validated = validate_csv(
        path,
        path_alias="docs/household_power_consumption.csv",
        expected_sha256=BUILTIN_CSV_SHA256,
    )

    result = preprocess_dataset(validated, config)
    data_dir = tmp_path / "data"
    record, manifest = write_preprocess_artifacts(validated, result, config, data_dir=data_dir)

    assert len(result.minute_frame) == 260_640
    assert int(result.minute_frame["imputed_mask"].sum()) == 48
    assert int(result.minute_frame["long_gap_mask"].sum()) == 3_723
    assert len(result.aggregated_frame) == 17_376
    assert record.split_counts == {"train": 11_520, "validation": 2_976, "test": 2_880}
    assert manifest.splits["counts"] == record.split_counts
    assert manifest.source_sha256 == BUILTIN_CSV_SHA256
    assert manifest.preprocessing["negative_unmetered_rows"] >= 11

    minute_path = data_dir / "interim" / result.preprocess_id / "minute.parquet"
    processed_path = data_dir / "processed" / result.preprocess_id / "power_15min.parquet"
    manifest_path = data_dir / "manifests" / f"{validated.dataset.dataset_id}.json"
    assert len(pd.read_parquet(minute_path)) == 260_640
    assert len(pd.read_parquet(processed_path)) == 17_376
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["config_hash"] == result.config_hash
    assert payload["artifacts"]["processed"] == record.processed_path_alias
