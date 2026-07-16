from __future__ import annotations

import hashlib

from psycopg2.extras import Json, execute_values

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.connection import connect
from crawler_machine.worker.store import ClaimedOperation


class PostgresOperationStore:
    def __init__(self, config: PostgresConfig, lease_seconds: int = 60) -> None:
        self._config = config
        self._lease_seconds = lease_seconds

    def register_worker(
        self, worker_key: str, version: str, capacity: dict[str, int]
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.worker_instances
                            (worker_key, version, capacity, health_state, last_heartbeat_at, created_at, updated_at)
                        VALUES (%s, %s, %s, 'healthy', NOW(), NOW(), NOW())
                        ON CONFLICT (worker_key) DO UPDATE SET
                            version = EXCLUDED.version,
                            capacity = EXCLUDED.capacity,
                            health_state = 'healthy',
                            last_heartbeat_at = NOW(),
                            updated_at = NOW()
                        """,
                        (worker_key, version, Json(capacity)),
                    )

    def claim(
        self, worker_key: str, supported_types: tuple[str, ...]
    ) -> ClaimedOperation | None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"""
                        WITH candidate AS (
                            SELECT id
                            FROM crawler.operations
                            WHERE state = 'queued' AND type = ANY(%s)
                            ORDER BY created_at, id
                            FOR UPDATE SKIP LOCKED
                            LIMIT 1
                        )
                        UPDATE crawler.operations AS operation
                        SET state = 'running',
                            worker_instance_id = (
                                SELECT id FROM crawler.worker_instances WHERE worker_key = %s
                            ),
                            stage = 'claimed',
                            claimed_at = NOW(),
                            heartbeat_at = NOW(),
                            lease_expires_at = NOW() + INTERVAL '{self._lease_seconds} seconds',
                            updated_at = NOW()
                        FROM candidate
                        WHERE operation.id = candidate.id
                        RETURNING operation.id, operation.type, operation.crawl_agency_id, operation.plan
                        """,
                        (list(supported_types), worker_key),
                    )
                    row = cursor.fetchone()

        if row is None:
            return None
        return ClaimedOperation(id=row[0], type=row[1], crawl_agency_id=row[2], plan=row[3])

    def heartbeat(
        self,
        operation_id: int,
        worker_key: str,
        stage: str,
        percentage: int,
        processed: int,
        total: int,
        message: str,
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.worker_instances
                        SET health_state = 'healthy', last_heartbeat_at = NOW(), updated_at = NOW()
                        WHERE worker_key = %s
                        """,
                        (worker_key,),
                    )
                    cursor.execute(
                        f"""
                        UPDATE crawler.operations
                        SET stage = %s,
                            progress_percentage = %s,
                            processed_items = %s,
                            total_items = %s,
                            progress_message = %s,
                            heartbeat_at = NOW(),
                            lease_expires_at = NOW() + INTERVAL '{self._lease_seconds} seconds',
                            updated_at = NOW()
                        WHERE id = %s
                          AND state = 'running'
                          AND worker_instance_id = (
                              SELECT id FROM crawler.worker_instances WHERE worker_key = %s
                          )
                        """,
                        (stage, percentage, processed, total, message, operation_id, worker_key),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("operation lease is no longer owned by this worker")

    def complete_discovery(
        self, operation_id: int, worker_key: str, urls: list[str]
    ) -> None:
        unique_urls = list(dict.fromkeys(urls))
        content_hash = hashlib.sha256("\n".join(unique_urls).encode()).hexdigest()

        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT operation.crawl_agency_id
                        FROM crawler.operations AS operation
                        JOIN crawler.worker_instances AS worker
                          ON worker.id = operation.worker_instance_id
                        WHERE operation.id = %s
                          AND operation.state = 'running'
                          AND worker.worker_key = %s
                        FOR UPDATE
                        """,
                        (operation_id, worker_key),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("operation is terminal or owned by another worker")

                    cursor.execute(
                        """
                        INSERT INTO crawler.discovery_snapshots
                            (operation_id, crawl_agency_id, url_count, content_hash, created_at)
                        VALUES (%s, %s, %s, %s, NOW())
                        RETURNING id
                        """,
                        (operation_id, row[0], len(unique_urls), content_hash),
                    )
                    snapshot_id = cursor.fetchone()[0]

                    if unique_urls:
                        execute_values(
                            cursor,
                            """
                            INSERT INTO crawler.discovery_snapshot_urls
                                (discovery_snapshot_id, url, url_hash, created_at)
                            VALUES %s
                            """,
                            [
                                (
                                    snapshot_id,
                                    url,
                                    hashlib.sha256(url.encode()).hexdigest(),
                                )
                                for url in unique_urls
                            ],
                            template="(%s, %s, %s, NOW())",
                        )

                    cursor.execute(
                        """
                        UPDATE crawler.operations
                        SET state = 'succeeded',
                            stage = 'completed',
                            progress_percentage = 100,
                            processed_items = %s,
                            total_items = %s,
                            progress_message = 'Discovery snapshot persisted',
                            result = %s,
                            completed_at = NOW(),
                            lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE id = %s AND state = 'running'
                        """,
                        (
                            len(unique_urls),
                            len(unique_urls),
                            Json({"discovery_snapshot_id": snapshot_id}),
                            operation_id,
                        ),
                    )

    def fail(
        self, operation_id: int, worker_key: str, code: str, message: str
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.operations AS operation
                        SET state = 'failed',
                            stage = 'failed',
                            error_code = %s,
                            error_message = %s,
                            completed_at = NOW(),
                            lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE operation.id = %s
                          AND operation.state = 'running'
                          AND operation.worker_instance_id = (
                              SELECT id FROM crawler.worker_instances WHERE worker_key = %s
                          )
                        """,
                        (code, message[:4000], operation_id, worker_key),
                    )
