from __future__ import annotations

import os
import json
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


def test_worker_persists_profile_validation_evidence_atomically() -> None:
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
        cursor.execute("SELECT to_regclass('crawler.profile_validation_reports')")
        if cursor.fetchone()[0] is None:
            connection.close()
            pytest.skip("Laravel profile validation migrations are not installed")

    try:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO users (name, email, phone, person_type, username, password, created_at, updated_at)
                    VALUES ('Validation Test', %s, '0000000000', 'F', %s, 'test', NOW(), NOW())
                    RETURNING id
                    """,
                    (f"validation-{suffix}@example.com", f"validation-{suffix}"),
                )
                user_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.crawl_agencies
                        (name, slug, base_url, root_domain, created_at, updated_at)
                    VALUES ('Validation Source', %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        f"validation-{suffix}",
                        f"https://{suffix}.example.com",
                        f"{suffix}.example.com",
                    ),
                )
                agency_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.market_data_contract_versions
                        (version, status, fields, affected_agency_ids, created_by, created_at, updated_at)
                    VALUES ((SELECT COALESCE(MAX(version), 0) + 1 FROM crawler.market_data_contract_versions),
                            'draft', %s, '[]', %s, NOW(), NOW())
                    RETURNING id
                    """,
                    ('[{"name":"title","type":"string","required":true}]', user_id),
                )
                contract_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.operations
                        (type, state, requested_by, crawl_agency_id, plan, created_at, updated_at)
                    VALUES ('discovery', 'succeeded', %s, %s, '{}', NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, agency_id),
                )
                discovery_operation_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.discovery_snapshots
                        (operation_id, crawl_agency_id, url_count, content_hash, created_at)
                    VALUES (%s, %s, 1, %s, NOW()) RETURNING id
                    """,
                    (discovery_operation_id, agency_id, "f" * 64),
                )
                snapshot_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.operations
                        (type, state, requested_by, crawl_agency_id,
                         market_data_contract_version_id, plan, created_at, updated_at)
                    VALUES ('profile_generation', 'succeeded', %s, %s, %s, '{}', NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, agency_id, contract_id),
                )
                generation_operation_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO crawler.extraction_profiles
                        (crawl_agency_id, discovery_snapshot_id,
                         market_data_contract_version_id, created_by_operation_id,
                         version, status, sample_url, schemas, strategies, fields,
                         parameters, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, 1, 'candidate', %s, %s, %s, %s, '{}', NOW(), NOW())
                    RETURNING id
                    """,
                    (
                        agency_id,
                        snapshot_id,
                        contract_id,
                        generation_operation_id,
                        f"https://{suffix}.example.com/property/1",
                        '{"xpath":{}}',
                        '["xpath"]',
                        '[{"name":"title","type":"string","required":true}]',
                    ),
                )
                profile_id = cursor.fetchone()[0]
                plan = (
                    '{"extraction_profile_id":'
                    + str(profile_id)
                    + ',"urls":["https://example.com/property/1"]}'
                )
                cursor.execute(
                    """
                    INSERT INTO crawler.operations
                        (type, state, requested_by, crawl_agency_id,
                         market_data_contract_version_id, plan, created_at, updated_at)
                    VALUES ('profile_validation', 'queued', %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, agency_id, contract_id, plan),
                )
                operation_id = cursor.fetchone()[0]

        store = PostgresOperationStore(config)
        worker_key = f"validation-{suffix}"
        store.register_worker(worker_key, "test", {"concurrency": 1})
        operation = store.claim(worker_key, ("profile_validation",))
        assert operation is not None
        assert operation.id == operation_id
        store.complete_validation(
            operation_id,
            worker_key,
            {
                "sampled_url_count": 1,
                "valid_record_count": 1,
                "valid_ratio": 1.0,
                "required_field_coverage": {"title": 1.0},
                "blocking_failures": [],
                "warnings": ["reviewed warning"],
                "eligible": True,
                "records": [
                    {
                        "url": "https://example.com/property/1",
                        "raw_data": {"title": "Raw"},
                        "normalized_data": {"title": "Raw"},
                        "errors": [],
                        "field_presence": {"title": True},
                        "is_valid": True,
                    }
                ],
            },
        )

        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT operation.state, report.eligible, record.raw_data->>'title'
                    FROM crawler.operations AS operation
                    JOIN crawler.profile_validation_reports AS report ON report.operation_id = operation.id
                    JOIN crawler.profile_validation_records AS record
                      ON record.profile_validation_report_id = report.id
                    WHERE operation.id = %s
                    """,
                    (operation_id,),
                )
                assert cursor.fetchone() == ("succeeded", True, "Raw")

        with connection:
            with connection.cursor() as cursor:
                production_plan = {
                    "crawl_agency_id": agency_id,
                    "discovery": {"mode": "existing", "snapshot_id": snapshot_id},
                    "extraction_profile": {"id": profile_id},
                    "market_data_contract": {"id": contract_id},
                    "quality_policy": {
                        "id": cursor.execute(
                            "SELECT id FROM crawler.quality_policy_versions WHERE status = 'active' LIMIT 1"
                        )
                        or cursor.fetchone()[0]
                    },
                }
                cursor.execute(
                    """
                    INSERT INTO crawler.operations
                        (type, state, requested_by, crawl_agency_id,
                         market_data_contract_version_id, plan, created_at, updated_at)
                    VALUES ('production_crawl', 'queued', %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (user_id, agency_id, contract_id, json.dumps(production_plan)),
                )
                production_operation_id = cursor.fetchone()[0]

        production_operation = store.claim(worker_key, ("production_crawl",))
        assert production_operation is not None
        assert production_operation.id == production_operation_id
        store.complete_production_crawl(
            production_operation_id,
            worker_key,
            {
                "technical_state": "succeeded",
                "result_kind": "full",
                "publishable": True,
                "discovery": {"mode": "existing", "snapshot_id": snapshot_id, "urls": []},
                "raw_properties": [
                    {
                        "url": "https://example.com/property/1",
                        "payload": {"url": "https://example.com/property/1", "valor": "200000"},
                        "extraction_trace": {"valor": "xpath"},
                        "errors": [],
                    }
                ],
                "market_properties": [
                    {
                        "raw_index": 0,
                        "payload": {"url": "https://example.com/property/1", "valor": 200000},
                        "normalization_warnings": [],
                        "extraction_trace": {"valor": "xpath"},
                    }
                ],
                "rejected_properties": [],
                "errors": [],
                "artifacts": [{"kind": "execution_summary", "payload": {"normalized": 1}}],
                "technical_logs": [
                    {"level": "info", "stage": "completed", "message": "done", "context": {}}
                ],
            },
        )
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT run.id, run.publication_state, market.payload->>'valor'
                    FROM crawler.crawl_runs AS run
                    JOIN crawler.market_properties AS market ON market.crawler_run_id = run.id
                    WHERE run.operation_id = %s
                    """,
                    (production_operation_id,),
                )
                run_id, publication_state, persisted_value = cursor.fetchone()
                assert publication_state == "candidate"
                assert persisted_value == "200000"
    finally:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM crawler.profile_validation_records WHERE profile_validation_report_id IN (SELECT id FROM crawler.profile_validation_reports WHERE operation_id = %s)",
                    (locals().get("operation_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.profile_validation_reports WHERE operation_id = %s",
                    (locals().get("operation_id", -1),),
                )
                for table in (
                    "technical_logs",
                    "crawler_artifacts",
                    "rejected_properties",
                    "market_properties",
                    "raw_properties",
                ):
                    cursor.execute(
                        f"DELETE FROM crawler.{table} WHERE crawler_run_id = %s",
                        (locals().get("run_id", -1),),
                    )
                cursor.execute(
                    "DELETE FROM crawler.crawl_runs WHERE id = %s",
                    (locals().get("run_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.extraction_profiles WHERE id = %s",
                    (locals().get("profile_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.discovery_snapshots WHERE id = %s",
                    (locals().get("snapshot_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.operations WHERE id IN (%s, %s, %s, %s)",
                    (
                        locals().get("operation_id", -1),
                        locals().get("production_operation_id", -1),
                        locals().get("generation_operation_id", -1),
                        locals().get("discovery_operation_id", -1),
                    ),
                )
                cursor.execute(
                    "DELETE FROM crawler.worker_instances WHERE worker_key = %s",
                    (locals().get("worker_key", "missing"),),
                )
                cursor.execute(
                    "DELETE FROM crawler.market_data_contract_versions WHERE id = %s",
                    (locals().get("contract_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM crawler.crawl_agencies WHERE id = %s",
                    (locals().get("agency_id", -1),),
                )
                cursor.execute(
                    "DELETE FROM users WHERE id = %s", (locals().get("user_id", -1),)
                )
        connection.close()
