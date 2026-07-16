from __future__ import annotations

import os
import uuid

import psycopg2
import pytest

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.postgres_store import PostgresOperationStore


pytestmark = pytest.mark.skipif(
    not os.getenv("DB_HOST"), reason="Postgres integration database not configured"
)


def test_worker_claims_and_persists_discovery_in_laravel_schema() -> None:
    config = PostgresConfig.from_env()
    assert config is not None
    suffix = uuid.uuid4().hex[:12]
    connection = psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
    )
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('crawler.operations')")
        if cursor.fetchone()[0] is None:
            connection.close()
            pytest.skip("Laravel crawler operation migrations are not installed")

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (name, email, phone, person_type, username, password, created_at, updated_at)
                    VALUES ('Contract Test', %s, '0000000000', 'F', %s, 'test', NOW(), NOW())
                    RETURNING id
                    """,
                    (f"contract-{suffix}@example.com", f"contract-{suffix}"),
                )
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.crawl_agencies
                        (name, slug, base_url, root_domain, created_at, updated_at)
                    VALUES ('Contract Source', %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        f"contract-{suffix}",
                        f"https://{suffix}.example.com",
                        f"{suffix}.example.com",
                    ),
                )
                agency_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.operations
                        (type, state, requested_by, crawl_agency_id, plan, created_at, updated_at)
                    VALUES ('discovery', 'queued', %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, agency_id, '{"base_url":"https://example.com"}'),
                )
                operation_id = cursor.fetchone()[0]

        store = PostgresOperationStore(config)
        worker_key = f"integration-{suffix}"
        store.register_worker(worker_key, "test", {"concurrency": 1})
        operation = store.claim(worker_key, ("discovery",))
        assert operation is not None
        assert operation.id == operation_id
        store.heartbeat(operation_id, worker_key, "discovery", 50, 1, 2, "working")
        store.complete_discovery(
            operation_id,
            worker_key,
            ["https://example.com/imovel/1", "https://example.com/imovel/2"],
        )

        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT operation.state, operation.progress_percentage, snapshot.url_count
                    FROM crawler.operations AS operation
                    JOIN crawler.discovery_snapshots AS snapshot ON snapshot.operation_id = operation.id
                    WHERE operation.id = %s
                    """,
                    (operation_id,),
                )
                assert cursor.fetchone() == ("succeeded", 100, 2)
    finally:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM crawler.discovery_snapshot_urls WHERE discovery_snapshot_id IN (SELECT id FROM crawler.discovery_snapshots WHERE operation_id = %s)",
                    (locals().get("operation_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.discovery_snapshots WHERE operation_id = %s",
                    (locals().get("operation_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.operations WHERE id = %s",
                    (locals().get("operation_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.worker_instances WHERE worker_key = %s",
                    (locals().get("worker_key", "missing"),),
                )
                cursor.execute(
                    "DELETE FROM crawler.crawl_agencies WHERE id = %s",
                    (locals().get("agency_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM users WHERE id = %s", (locals().get("user_id", -1),)
                )
        connection.close()
