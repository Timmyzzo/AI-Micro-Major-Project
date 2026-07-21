"""Validate PowerInsight source data without writing processing artifacts."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from powerinsight.config import load_settings
from powerinsight.data import BUILTIN_CSV_SHA256, validate_csv
from powerinsight.paths import PROJECT_ROOT, ProjectPaths, display_path


def main(argv: Sequence[str] | None = None) -> int:
    """Validate the configured built-in CSV and return a stable process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    args = parser.parse_args(argv)
    try:
        settings = load_settings(config_path=args.config, project_root=PROJECT_ROOT)
        paths = ProjectPaths.from_settings(settings)
        alias = display_path(paths.builtin_csv, root=paths.root)
        result = validate_csv(
            paths.builtin_csv,
            path_alias=alias,
            expected_sha256=BUILTIN_CSV_SHA256,
            raw_cadence=settings.data.raw_cadence,
            short_gap_max_minutes=settings.data.short_gap_max_minutes,
        )
    except Exception as exc:
        safe_error = str(exc).replace(str(PROJECT_ROOT), ".")
        print(json.dumps({"status": "blocked", "error": safe_error}, ensure_ascii=False))
        return 2

    report = result.report
    longest = max(report.missing_blocks, key=lambda block: block.length_minutes, default=None)
    summary = {
        "status": report.status,
        "dataset_id": result.dataset.dataset_id,
        "source_path_alias": result.dataset.path_alias,
        "sha256": result.dataset.sha256,
        "rows": report.row_count,
        "fields": result.dataset.field_count,
        "start_time": result.dataset.start_time,
        "end_time": result.dataset.end_time,
        "cadence": result.dataset.cadence,
        "measurement_missing_rows": report.measurement_missing_row_count,
        "missing_blocks": len(report.missing_blocks),
        "longest_missing_block_minutes": longest.length_minutes if longest else 0,
        "score": report.score,
        "issues": {
            "errors": report.issue_count("error"),
            "warnings": report.issue_count("warning"),
            "information": report.issue_count("information"),
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 1 if report.status == "blocked" else 0


if __name__ == "__main__":
    raise SystemExit(main())
