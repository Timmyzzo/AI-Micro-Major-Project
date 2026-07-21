"""Generate repeatable PowerInsight M2 data artifacts without training models."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from powerinsight.paths import PROJECT_ROOT
from powerinsight.services.data_service import DataService
from powerinsight.services.runtime import initialize_runtime


def main(argv: Sequence[str] | None = None) -> int:
    """Prepare configured data and print only non-sensitive aliases and statistics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/default.yaml"))
    args = parser.parse_args(argv)
    try:
        context = initialize_runtime(config_path=args.config, project_root=PROJECT_ROOT)
        result = DataService(context).prepare_builtin()
    except Exception as exc:
        safe_error = str(exc).replace(str(PROJECT_ROOT), ".")
        print(json.dumps({"status": "failed", "error": safe_error}, ensure_ascii=False))
        return 2

    output = {
        "status": "completed",
        "dataset_id": result.validation.dataset.dataset_id,
        "preprocess_id": result.processed.preprocess_id,
        "config_hash": result.processed.config_hash,
        "source_path_alias": result.validation.dataset.path_alias,
        "minute_rows": result.processed.minute_rows,
        "processed_rows": result.processed.processed_rows,
        "split_counts": result.processed.split_counts,
        "artifacts": {
            "minute": result.processed.minute_path_alias,
            "processed": result.processed.processed_path_alias,
            "manifest": result.processed.manifest_path_alias,
        },
        "timings_seconds": {
            "validation": round(result.timings.validation_seconds, 4),
            "preprocessing_write": round(result.timings.preprocessing_write_seconds, 4),
            "parquet_read": round(result.timings.parquet_read_seconds, 4),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
