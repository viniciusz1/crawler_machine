from __future__ import annotations

import os


def is_test_database_name(database: str | None) -> bool:
    normalized = (database or "").strip().lower()
    return normalized.endswith("_test") or normalized.endswith("-test")


def database_tests_enabled() -> bool:
    return bool(os.getenv("DB_HOST")) and is_test_database_name(
        os.getenv("DB_DATABASE")
    )
