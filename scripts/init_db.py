"""Initialize the configured PowerInsight SQLite metadata database."""

from __future__ import annotations

from powerinsight.paths import display_path
from powerinsight.services.runtime import initialize_runtime


def main() -> int:
    """Initialize the database idempotently and print a non-sensitive summary."""
    context = initialize_runtime()
    print(
        "SQLite initialized:",
        display_path(context.paths.database_path, root=context.paths.root),
        context.status.database_status,
    )
    return 0 if context.status.database_accessible else 1


if __name__ == "__main__":
    raise SystemExit(main())
