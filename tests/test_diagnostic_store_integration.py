"""Verify durable evidence against the Laravel-owned Postgres schema."""

from contextlib import closing
from uuid import uuid4

import psycopg2
import pytest

from crawler_machine.diagnostics import DiagnosticEvent
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.postgres_store import PostgresOperationStore
from tests.database_safety import database_tests_enabled

pytestmark = pytest.mark.skipif(
    not database_tests_enabled(), reason="An explicit *_test database is required"
)


def test_diagnostics_survive_before_a_run_and_require_current_lease():
    config = PostgresConfig.from_env()
    assert config is not None
    suffix = uuid4().hex
    worker_key = "diagnostics-" + suffix
    other_key = "other-" + suffix
    with closing(
        psycopg2.connect(
            host=config.host,
            port=config.port,
            dbname=config.database,
            user=config.user,
            password=config.password,
        )
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('crawler.operation_diagnostics')")
            if cursor.fetchone()[0] is None:
                pytest.skip("Apply Laravel diagnostic migrations first")
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO users (name,email,phone,person_type,username,password,created_at,updated_at)
                    VALUES ('Diagnostic test',%s,'0000000000','F',%s,'test',NOW(),NOW()) RETURNING id""",
                    (suffix + "@example.com", suffix),
                )
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    """INSERT INTO crawler.operations (type,state,requested_by,plan,created_at,updated_at)
                    VALUES ('diagnostic_probe','queued',%s,'{}',NOW(),NOW()) RETURNING id""",
                    (user_id,),
                )
                operation_id = cursor.fetchone()[0]
        try:
            store = PostgresOperationStore(config)
            store.register_worker(worker_key, "test", {"concurrency": 1})
            store.register_worker(other_key, "test", {"concurrency": 1})
            claimed = store.claim(worker_key, ("diagnostic_probe",))
            assert claimed is not None and claimed.id == operation_id
            event = DiagnosticEvent(
                kind="attempt",
                stage="extraction",
                outcome="failed",
                url="https://example.com/imovel/1",
                strategy="xpath",
                error_code="strategy_failed",
            )
            store.record_diagnostic(operation_id, worker_key, event)
            store.record_diagnostic(operation_id, worker_key, event)
            with pytest.raises(RuntimeError, match="lease"):
                store.record_diagnostic(operation_id, other_key, event)
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT count(*) FROM crawler.operation_diagnostics WHERE operation_id=%s",
                        (operation_id,),
                    )
                    assert cursor.fetchone()[0] == 1
                    cursor.execute(
                        "SELECT count(*) FROM crawler.crawl_runs WHERE operation_id=%s",
                        (operation_id,),
                    )
                    assert cursor.fetchone()[0] == 0
                    cursor.execute(
                        "UPDATE crawler.operations SET lease_expires_at=NOW()-INTERVAL '1 minute' WHERE id=%s",
                        (operation_id,),
                    )
            with pytest.raises(RuntimeError, match="lease"):
                store.record_diagnostic(operation_id, worker_key, event)
        finally:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM crawler.operation_diagnostics WHERE operation_id=%s",
                        (operation_id,),
                    )
                    cursor.execute(
                        "DELETE FROM crawler.operations WHERE id=%s", (operation_id,)
                    )
                    cursor.execute(
                        "DELETE FROM crawler.worker_instances WHERE worker_key IN (%s,%s)",
                        (worker_key, other_key),
                    )
                    cursor.execute("DELETE FROM users WHERE id=%s", (user_id,))
