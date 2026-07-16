from __future__ import annotations

from unittest.mock import MagicMock, patch

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.postgres_store import PostgresOperationStore


def test_claim_uses_skip_locked_and_assigns_a_lease_atomically() -> None:
    config = PostgresConfig("localhost", 5432, "test", "user", "pass")
    connection = MagicMock()
    cursor = MagicMock()
    connection.cursor.return_value.__enter__.return_value = cursor
    cursor.fetchone.return_value = (
        7,
        "discovery",
        42,
        {"base_url": "https://agency.example.com"},
    )

    with patch("psycopg2.connect", return_value=connection):
        operation = PostgresOperationStore(config).claim("worker-a", ("discovery",))

    assert operation is not None
    assert operation.id == 7
    sql, parameters = cursor.execute.call_args.args
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "lease_expires_at" in sql
    assert parameters == (["discovery"], "worker-a")
