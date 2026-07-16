from __future__ import annotations

import hashlib
from typing import Any

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
                              AND (
                                type <> 'production_crawl'
                                OR NOT EXISTS (
                                    SELECT 1 FROM crawler.operations AS active
                                    WHERE active.type = 'production_crawl'
                                      AND active.crawl_agency_id = crawler.operations.crawl_agency_id
                                      AND active.state IN ('running', 'cancellation_requested')
                                )
                              )
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

    def complete_sample_suggestion(
        self, operation_id: int, worker_key: str, sample_url: str | None
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.operations AS operation
                        SET state = 'succeeded',
                            stage = 'completed',
                            progress_percentage = 100,
                            progress_message = 'Sample URL suggestion completed',
                            result = %s,
                            completed_at = NOW(),
                            lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE operation.id = %s
                          AND operation.state = 'running'
                          AND operation.worker_instance_id = (
                              SELECT id FROM crawler.worker_instances WHERE worker_key = %s
                          )
                        """,
                        (Json({"sample_url": sample_url}), operation_id, worker_key),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("sample suggestion operation is no longer owned")

    def complete_profile(
        self, operation_id: int, worker_key: str, profile: dict[str, Any]
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT operation.crawl_agency_id, operation.plan
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
                        raise RuntimeError("profile operation is terminal or owned by another worker")
                    agency_id, plan = row
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", (agency_id,))
                    cursor.execute(
                        """
                        SELECT COALESCE(MAX(version), 0) + 1
                        FROM crawler.extraction_profiles
                        WHERE crawl_agency_id = %s
                        """,
                        (agency_id,),
                    )
                    version = cursor.fetchone()[0]
                    cursor.execute(
                        """
                        INSERT INTO crawler.extraction_profiles
                            (crawl_agency_id, discovery_snapshot_id,
                             market_data_contract_version_id, created_by_operation_id,
                             version, status, sample_url, schemas, strategies, fields,
                             parameters, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, 'candidate', %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING id
                        """,
                        (
                            agency_id,
                            plan["discovery_snapshot_id"],
                            plan["market_data_contract_version_id"],
                            operation_id,
                            version,
                            plan["sample_url"],
                            Json(profile["schemas"]),
                            Json(profile["strategies"]),
                            Json(profile["fields"]),
                            Json(profile.get("parameters", {})),
                        ),
                    )
                    profile_id = cursor.fetchone()[0]
                    cursor.execute(
                        """
                        UPDATE crawler.operations
                        SET state = 'succeeded', stage = 'completed',
                            progress_percentage = 100,
                            progress_message = 'Extraction Profile candidate persisted',
                            result = %s, completed_at = NOW(), lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE id = %s AND state = 'running'
                        """,
                        (Json({"extraction_profile_id": profile_id}), operation_id),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("operation is terminal or owned by another worker")

    def complete_validation(
        self, operation_id: int, worker_key: str, report: dict[str, Any]
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT operation.plan
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
                        raise RuntimeError("validation operation is terminal or owned by another worker")
                    plan = row[0]

                    cursor.execute(
                        """
                        INSERT INTO crawler.profile_validation_reports
                            (operation_id, extraction_profile_id, sampled_url_count,
                             valid_record_count, valid_ratio, required_field_coverage,
                             blocking_failures, warnings, eligible, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING id
                        """,
                        (
                            operation_id,
                            plan["extraction_profile_id"],
                            report["sampled_url_count"],
                            report["valid_record_count"],
                            report["valid_ratio"],
                            Json(report["required_field_coverage"]),
                            Json(report["blocking_failures"]),
                            Json(report["warnings"]),
                            report["eligible"],
                        ),
                    )
                    report_id = cursor.fetchone()[0]

                    records = report.get("records", [])
                    if records:
                        execute_values(
                            cursor,
                            """
                            INSERT INTO crawler.profile_validation_records
                                (profile_validation_report_id, url, raw_data,
                                 normalized_data, errors, field_presence, is_valid,
                                 created_at, updated_at)
                            VALUES %s
                            """,
                            [
                                (
                                    report_id,
                                    record["url"],
                                    Json(record["raw_data"]),
                                    Json(record["normalized_data"]),
                                    Json(record["errors"]),
                                    Json(record["field_presence"]),
                                    record["is_valid"],
                                )
                                for record in records
                            ],
                            template="(%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())",
                        )

                    cursor.execute(
                        """
                        UPDATE crawler.operations
                        SET state = 'succeeded', stage = 'completed',
                            progress_percentage = 100,
                            processed_items = %s, total_items = %s,
                            progress_message = 'Profile validation report persisted',
                            result = %s, completed_at = NOW(), lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE id = %s AND state = 'running'
                        """,
                        (
                            report["sampled_url_count"],
                            report["sampled_url_count"],
                            Json({"profile_validation_report_id": report_id}),
                            operation_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("validation operation is no longer owned")

    def complete_production_crawl(
        self, operation_id: int, worker_key: str, result: dict[str, Any]
    ) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT operation.crawl_agency_id, operation.plan
                        FROM crawler.operations AS operation
                        JOIN crawler.worker_instances AS worker
                          ON worker.id = operation.worker_instance_id
                        WHERE operation.id = %s
                          AND operation.state IN ('running', 'cancellation_requested')
                          AND worker.worker_key = %s
                        FOR UPDATE
                        """,
                        (operation_id, worker_key),
                    )
                    row = cursor.fetchone()
                    if row is None:
                        raise RuntimeError("production operation is terminal or owned by another worker")
                    agency_id, plan = row
                    discovery = result["discovery"]
                    snapshot_id = discovery.get("snapshot_id")
                    if discovery["mode"] == "fresh":
                        urls = list(dict.fromkeys(discovery.get("urls", [])))
                        content_hash = hashlib.sha256("\n".join(urls).encode()).hexdigest()
                        cursor.execute(
                            """
                            INSERT INTO crawler.discovery_snapshots
                                (operation_id, crawl_agency_id, url_count, content_hash, created_at)
                            VALUES (%s, %s, %s, %s, NOW()) RETURNING id
                            """,
                            (operation_id, agency_id, len(urls), content_hash),
                        )
                        snapshot_id = cursor.fetchone()[0]
                        if urls:
                            execute_values(
                                cursor,
                                """
                                INSERT INTO crawler.discovery_snapshot_urls
                                    (discovery_snapshot_id, url, url_hash, created_at)
                                VALUES %s
                                """,
                                [
                                    (snapshot_id, url, hashlib.sha256(url.encode()).hexdigest())
                                    for url in urls
                                ],
                                template="(%s, %s, %s, NOW())",
                            )

                    cursor.execute(
                        """
                        INSERT INTO crawler.crawl_runs
                            (operation_id, crawl_agency_id, discovery_snapshot_id,
                             extraction_profile_id, market_data_contract_version_id,
                             quality_policy_version_id, technical_state, result_kind,
                             publication_state, publishable, raw_count, normalized_count,
                             rejected_count, error_count, error_summary, started_at,
                             completed_at, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'candidate', %s,
                                %s, %s, %s, %s, %s, COALESCE(
                                    (SELECT claimed_at FROM crawler.operations WHERE id = %s), NOW()
                                ), NOW(), NOW(), NOW())
                        RETURNING id
                        """,
                        (
                            operation_id,
                            agency_id,
                            snapshot_id,
                            plan["extraction_profile"]["id"],
                            plan["market_data_contract"]["id"],
                            plan["quality_policy"]["id"],
                            result["technical_state"],
                            result["result_kind"],
                            result["publishable"],
                            len(result["raw_properties"]),
                            len(result["market_properties"]),
                            len(result["rejected_properties"]),
                            len(result["errors"]),
                            Json(result["errors"]),
                            operation_id,
                        ),
                    )
                    run_id = cursor.fetchone()[0]
                    raw_ids: list[int] = []
                    for raw in result["raw_properties"]:
                        cursor.execute(
                            """
                            INSERT INTO crawler.raw_properties
                                (crawler_run_id, url, payload, extraction_trace, errors, created_at)
                            VALUES (%s, %s, %s, %s, %s, NOW()) RETURNING id
                            """,
                            (
                                run_id,
                                raw.get("url"),
                                Json(raw["payload"]),
                                Json(raw["extraction_trace"]),
                                Json(raw["errors"]),
                            ),
                        )
                        raw_ids.append(cursor.fetchone()[0])

                    for market in result["market_properties"]:
                        payload = market["payload"]
                        raw_id = raw_ids[market["raw_index"]]
                        cursor.execute(
                            """
                            INSERT INTO crawler.market_properties
                                (crawler_run_id, raw_property_id, tipo, imobiliaria, valor,
                                 bairro, cidade, imagem, link_imovel, descricao, quartos,
                                 suites, banheiros, vagas, area, aceita_permuta, financiamento,
                                 piscina, churrasqueira, academia, salao_festas, playground,
                                 sacada, mobiliado, ar_condicionado, lavanderia, escritorio,
                                 closet, elevador, portaria_24h, andar, posicao_solar,
                                 ano_construcao, payload, normalization_warnings,
                                 extraction_trace, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                            """,
                            (
                                run_id,
                                raw_id,
                                payload.get("tipo_imovel", payload.get("tipo")),
                                payload.get("imobiliaria"),
                                payload.get("valor"),
                                payload.get("bairro"),
                                payload.get("cidade"),
                                payload.get("imagem"),
                                payload.get("url", payload.get("link_imovel")),
                                payload.get("descricao"),
                                payload.get("quartos"),
                                payload.get("suites"),
                                payload.get("banheiros"),
                                payload.get("vagas"),
                                payload.get("area_util", payload.get("area")),
                                payload.get("aceita_permuta"),
                                payload.get("financiamento"),
                                payload.get("piscina"),
                                payload.get("churrasqueira"),
                                payload.get("academia"),
                                payload.get("salao_festas"),
                                payload.get("playground"),
                                payload.get("sacada"),
                                payload.get("mobiliado"),
                                payload.get("ar_condicionado"),
                                payload.get("lavanderia"),
                                payload.get("escritorio"),
                                payload.get("closet"),
                                payload.get("elevador"),
                                payload.get("portaria_24h"),
                                payload.get("andar"),
                                payload.get("posicao_solar"),
                                payload.get("ano", payload.get("ano_construcao")),
                                Json(payload),
                                Json(market["normalization_warnings"]),
                                Json(market["extraction_trace"]),
                            ),
                        )

                    for rejected in result["rejected_properties"]:
                        cursor.execute(
                            """
                            INSERT INTO crawler.rejected_properties
                                (crawler_run_id, raw_property_id, url, payload,
                                 missing_fields, errors, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                            """,
                            (
                                run_id,
                                raw_ids[rejected["raw_index"]],
                                rejected.get("url"),
                                Json(rejected["payload"]),
                                Json(rejected["missing_fields"]),
                                Json(rejected["errors"]),
                            ),
                        )

                    for artifact in result.get("artifacts", []):
                        cursor.execute(
                            """
                            INSERT INTO crawler.crawler_artifacts
                                (crawler_run_id, kind, payload, created_at)
                            VALUES (%s, %s, %s, NOW())
                            """,
                            (run_id, artifact["kind"], Json(artifact["payload"])),
                        )
                    for log in result.get("technical_logs", []):
                        cursor.execute(
                            """
                            INSERT INTO crawler.technical_logs
                                (crawler_run_id, level, stage, message, context, created_at)
                            VALUES (%s, %s, %s, %s, %s, NOW())
                            """,
                            (
                                run_id,
                                log["level"],
                                log.get("stage"),
                                log["message"],
                                Json(log.get("context", {})),
                            ),
                        )

                    operation_state = {
                        "succeeded": "succeeded",
                        "cancelled": "cancelled",
                    }.get(result["technical_state"], "failed")
                    cursor.execute(
                        """
                        UPDATE crawler.operations
                        SET state = %s, stage = %s, progress_percentage = 100,
                            processed_items = %s, total_items = %s,
                            progress_message = %s, result = %s,
                            error_code = %s, error_message = %s,
                            completed_at = NOW(), lease_expires_at = NULL, updated_at = NOW()
                        WHERE id = %s AND state IN ('running', 'cancellation_requested')
                        """,
                        (
                            operation_state,
                            "completed" if operation_state == "succeeded" else operation_state,
                            len(result["raw_properties"]),
                            len(discovery.get("urls", [])),
                            "Production crawl persisted",
                            Json(
                                {
                                    "crawl_run_id": run_id,
                                    "discovery_snapshot_id": snapshot_id,
                                    "result_kind": result["result_kind"],
                                    "publication_state": "candidate",
                                }
                            ),
                            None if operation_state == "succeeded" else (
                                "cancelled_by_operator"
                                if operation_state == "cancelled"
                                else "partial_crawl"
                            ),
                            None
                            if operation_state == "succeeded"
                            else (
                                "Production crawl cancelled after preserving partial results"
                                if operation_state == "cancelled"
                                else "Production crawl failed after preserving partial results"
                            ),
                            operation_id,
                        ),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("production operation is no longer owned")

    def cancellation_requested(self, operation_id: int, worker_key: str) -> bool:
        with connect(self._config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT operation.state = 'cancellation_requested'
                    FROM crawler.operations AS operation
                    JOIN crawler.worker_instances AS worker
                      ON worker.id = operation.worker_instance_id
                    WHERE operation.id = %s AND worker.worker_key = %s
                    """,
                    (operation_id, worker_key),
                )
                row = cursor.fetchone()
                return bool(row and row[0])

    def cancel(self, operation_id: int, worker_key: str) -> None:
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.operations AS operation
                        SET state = 'cancelled', stage = 'cancelled',
                            progress_message = 'Cancelled cooperatively by worker',
                            completed_at = NOW(), lease_expires_at = NULL, updated_at = NOW()
                        WHERE operation.id = %s
                          AND operation.state IN ('running', 'cancellation_requested')
                          AND operation.worker_instance_id = (
                              SELECT id FROM crawler.worker_instances WHERE worker_key = %s
                          )
                        """,
                        (operation_id, worker_key),
                    )
                    if cursor.rowcount != 1:
                        raise RuntimeError("operation is no longer cancellable by this worker")

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
