"""Verify the reproducible PowerInsight development environment."""

from __future__ import annotations

import hashlib
import importlib
import json
import sqlite3
import sys
import tempfile
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path

import torch

from powerinsight.config import ConfigurationError
from powerinsight.paths import display_path
from powerinsight.services.runtime import RuntimeContext, initialize_runtime

EXPECTED_CSV_SHA256 = "C79E3E19348BF518748D63455F98B2F09DAF9B1A72FA3F42048FADD9A588225E"
PACKAGE_IMPORTS: tuple[tuple[str, str], ...] = (
    ("pandas", "pandas"),
    ("numpy", "numpy"),
    ("pyarrow", "pyarrow"),
    ("scikit-learn", "sklearn"),
    ("torch", "torch"),
    ("transformers", "transformers"),
    ("streamlit", "streamlit"),
    ("plotly", "plotly"),
)


@dataclass(frozen=True)
class CheckResult:
    """One non-sensitive environment check result."""

    name: str
    status: str
    detail: str


def main() -> int:
    """Run all checks and return 0 for pass/warning, 1 for failure, or 2 for config errors."""
    try:
        context = initialize_runtime()
    except ConfigurationError as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False))
        return 2

    results: list[CheckResult] = []
    results.append(
        CheckResult(
            name="python",
            status="pass" if sys.version_info[:2] == (3, 11) else "fail",
            detail=sys.version.split()[0],
        )
    )
    results.extend(_check_imports())
    results.append(
        CheckResult(
            name="powerinsight",
            status="pass",
            detail=metadata.version("powerinsight"),
        )
    )
    results.extend(_check_cuda())
    results.append(CheckResult("sqlite", "pass", sqlite3.sqlite_version))
    results.append(
        CheckResult(
            "database",
            "pass" if context.status.database_accessible else "fail",
            context.status.database_status,
        )
    )
    results.extend(_check_csv(context))
    results.extend(_check_writable_directories(context))
    results.append(
        CheckResult(
            "llm_configuration",
            "pass",
            "enabled and complete"
            if context.settings.llm_configured
            else "disabled; no key required",
        )
    )

    failed = [result for result in results if result.status == "fail"]
    output = {
        "status": "failed" if failed else "passed",
        "checks": [asdict(result) for result in results],
        "summary": {
            "passed": sum(result.status == "pass" for result in results),
            "warnings": sum(result.status == "warning" for result in results),
            "failed": len(failed),
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failed else 0


def _check_imports() -> list[CheckResult]:
    results: list[CheckResult] = []
    for distribution_name, import_name in PACKAGE_IMPORTS:
        try:
            importlib.import_module(import_name)
            installed_version = metadata.version(distribution_name)
        except (ImportError, metadata.PackageNotFoundError) as exc:
            results.append(CheckResult(distribution_name, "fail", str(exc)))
        else:
            results.append(CheckResult(distribution_name, "pass", installed_version))
    return results


def _check_cuda() -> list[CheckResult]:
    if not torch.cuda.is_available():
        return [CheckResult("cuda", "warning", "unavailable; CPU fallback remains supported")]
    try:
        tensor = torch.arange(4, dtype=torch.float32, device="cuda")
        result = float((tensor * tensor).sum().cpu().item())
        torch.cuda.synchronize()
        properties = torch.cuda.get_device_properties(0)
    except RuntimeError as exc:
        return [CheckResult("cuda", "fail", f"tensor operation failed: {exc}")]
    return [
        CheckResult("cuda", "pass", f"runtime {torch.version.cuda}; tensor checksum {result}"),
        CheckResult("gpu_name", "pass", torch.cuda.get_device_name(0)),
        CheckResult("gpu_memory_bytes", "pass", str(int(properties.total_memory))),
    ]


def _check_csv(context: RuntimeContext) -> list[CheckResult]:
    csv_path = context.paths.builtin_csv
    alias = display_path(csv_path, root=context.paths.root)
    if not csv_path.is_file():
        return [CheckResult("raw_csv", "fail", f"missing: {alias}")]
    actual_hash = _sha256(csv_path)
    return [
        CheckResult("raw_csv", "pass", f"exists: {alias}"),
        CheckResult(
            "raw_csv_sha256",
            "pass" if actual_hash == EXPECTED_CSV_SHA256 else "fail",
            actual_hash,
        ),
    ]


def _check_writable_directories(context: RuntimeContext) -> list[CheckResult]:
    results: list[CheckResult] = []
    for directory in context.paths.writable_directories:
        alias = display_path(directory, root=context.paths.root)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=directory):
                pass
        except OSError as exc:
            results.append(CheckResult(f"writable:{alias}", "fail", str(exc)))
        else:
            results.append(CheckResult(f"writable:{alias}", "pass", "writable"))
    return results


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


if __name__ == "__main__":
    raise SystemExit(main())
