from __future__ import annotations

import os
import shlex
import subprocess
import uuid
from typing import Any

import httpx
import psycopg2
import pytest

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.postgres_store import PostgresOperationStore
from crawler_machine.worker.runner import CrawlerWorker


pytestmark = pytest.mark.skipif(
    not all(
        [
            os.getenv("LARAVEL_CONTRACT_URL"),
            os.getenv("LARAVEL_CONTRACT_TOKEN"),
            os.getenv("DB_HOST"),
        ]
    ),
    reason="Laravel contract environment is not configured",
)


class ContractDiscoverer:
    def discover_sync(
        self, base_url: str, policy: dict[str, Any] | None = None
    ) -> list[str]:
        return [f"{base_url.rstrip('/')}/imovel/contract-1"]


class ContractProfileGenerator:
    def __init__(self) -> None:
        self.seen_policies: list[dict[str, Any]] = []

    def generate(
        self,
        sample_url: str,
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if extraction_policy is None:
            raise AssertionError("Laravel did not pin the extraction policy")
        self.seen_policies.append(dict(extraction_policy))
        return {
            "schemas": {
                "xpath": {
                    "baseSelector": "//body",
                    "fields": {"title": "//h1/text()"},
                }
            },
            "strategies": list(extraction_policy["strategies"]),
            "fields": fields,
            "parameters": {
                "adapter": "contract",
                "extraction_policy": dict(extraction_policy),
            },
        }


class ContractValidationExecutor:
    def __init__(self) -> None:
        self.seen_policies: list[dict[str, Any]] = []

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        policy = plan.get("extraction_policy")
        if not isinstance(policy, dict):
            raise AssertionError("Laravel did not pin the validation extraction policy")
        self.seen_policies.append(dict(policy))
        urls = list(plan["urls"])
        return {
            "sampled_url_count": len(urls),
            "valid_record_count": len(urls),
            "valid_ratio": 1.0,
            "required_field_coverage": {"title": 1.0},
            "blocking_failures": [],
            "warnings": [],
            "eligible": True,
            "records": [
                {
                    "url": url,
                    "raw_data": {"title": "Contract property"},
                    "normalized_data": {"title": "Contract property"},
                    "errors": [],
                    "field_presence": {"title": True},
                    "is_valid": True,
                }
                for url in urls
            ],
        }


class ContractProductionExecutor:
    def __init__(self) -> None:
        self.seen_plans: list[dict[str, Any]] = []

    def run(self, plan: dict[str, Any], should_cancel) -> dict[str, Any]:
        self.seen_plans.append(dict(plan))
        discovery = dict(plan["discovery"])
        urls = [f"{discovery['base_url'].rstrip('/')}/imovel/first-production"]
        discovery["urls"] = urls
        return {
            "technical_state": "succeeded",
            "result_kind": "full",
            "publishable": True,
            "discovery": discovery,
            "raw_properties": [
                {
                    "url": urls[0],
                    "payload": {
                        "url": urls[0],
                        "title": "Contract first production",
                    },
                    "extraction_trace": {"title": "xpath"},
                    "errors": [],
                }
            ],
            "market_properties": [
                {
                    "raw_index": 0,
                    "payload": {
                        "url": urls[0],
                        "title": "Contract first production",
                    },
                    "normalization_warnings": [],
                    "extraction_trace": {"title": "xpath"},
                }
            ],
            "rejected_properties": [],
            "errors": [],
            "artifacts": [],
            "technical_logs": [],
        }


def test_laravel_queues_python_claims_and_laravel_reads_discovery() -> None:
    suffix = uuid.uuid4().hex[:12]
    client = httpx.Client(
        base_url=os.environ["LARAVEL_CONTRACT_URL"].rstrip("/"),
        headers={
            "Authorization": f"Bearer {os.environ['LARAVEL_CONTRACT_TOKEN']}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    agency_response = client.post(
        "/api/v1/admin/crawler/crawl-agencies",
        json={
            "name": "Contract Source",
            "slug": f"contract-{suffix}",
            "base_url": f"https://{suffix}.example.com",
            "root_domain": f"{suffix}.example.com",
        },
    )
    agency_response.raise_for_status()
    agency = agency_response.json()["data"]
    contract_response = client.post(
        "/api/v1/admin/crawler/market-data-contracts",
        json={
            "fields": [
                {
                    "name": "title",
                    "type": "string",
                    "required": True,
                    "normalization": ["trim"],
                }
            ]
        },
    )
    contract_response.raise_for_status()
    contract = contract_response.json()["data"]
    client.post(
        f"/api/v1/admin/crawler/market-data-contracts/{contract['id']}/validate"
    ).raise_for_status()
    client.post(
        f"/api/v1/admin/crawler/market-data-contracts/{contract['id']}/activate"
    ).raise_for_status()
    operation_response = client.post(
        "/api/v1/admin/crawler/operations",
        json={
            "type": "discovery",
            "crawl_agency_id": agency["id"],
            "market_data_contract_version_id": contract["id"],
        },
    )
    operation_response.raise_for_status()
    operation = operation_response.json()["data"]

    config = PostgresConfig.from_env()
    assert config is not None
    worker = CrawlerWorker(
        store=PostgresOperationStore(config),
        discoverer=ContractDiscoverer(),
        worker_key=f"contract-worker-{suffix}",
        version="contract-test",
    )
    completed = _run_until_operation_succeeds(
        worker,
        client,
        operation["id"],
    )
    urls_response = client.get(
        f"/api/v1/admin/crawler/discovery-snapshots/{completed['discovery_snapshot_id']}/urls"
    )
    urls_response.raise_for_status()
    assert urls_response.json()["data"][0]["url"].endswith("/imovel/contract-1")


@pytest.mark.skipif(
    not all(
        [
            os.getenv("LARAVEL_CONTRACT_ARTISAN"),
            os.getenv("LARAVEL_CONTRACT_ARTISAN_CWD"),
        ]
    ),
    reason="Laravel onboarding coordinator command is not configured",
)
def test_automated_onboarding_reaches_durable_approval_pause() -> None:
    suffix = uuid.uuid4().hex[:12]
    client = httpx.Client(
        base_url=os.environ["LARAVEL_CONTRACT_URL"].rstrip("/"),
        headers={
            "Authorization": f"Bearer {os.environ['LARAVEL_CONTRACT_TOKEN']}",
            "Accept": "application/json",
        },
        timeout=10,
    )
    config = PostgresConfig.from_env()
    assert config is not None

    with psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE email = 'platform@imobiliaria.com'"
            )
            user_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO crawler.prospects
                    (root_domain, google_place_id, name, city, state, base_url,
                     source, automatic_classification, review_state, reviewed_by,
                     reviewed_at, review_reason, metadata, created_at, updated_at)
                VALUES (%s, %s, %s, 'Joinville', 'SC', %s, 'contract',
                        'candidate', 'approved', %s, NOW(),
                        'Approved by deterministic contract setup', '{}',
                        NOW(), NOW())
                RETURNING id
                """,
                (
                    f"{suffix}.example.com",
                    f"contract-{suffix}",
                    f"Contract Onboarding {suffix}",
                    f"https://{suffix}.example.com",
                    user_id,
                ),
            )
            prospect_id = cursor.fetchone()[0]

    promotion = client.post(f"/api/v1/admin/crawler/prospects/{prospect_id}/promote")
    promotion.raise_for_status()
    promoted = promotion.json()["data"]
    agency = promoted["crawl_agency"]

    discovery_strategy_key = f"contract_discoverer_{suffix}"
    discovery_strategy = client.post(
        "/api/v1/admin/crawler/discovery-strategies",
        json={
            "key": discovery_strategy_key,
            "label": f"Contract discoverer {suffix}",
            "safety_status": "safe",
        },
    )
    discovery_strategy.raise_for_status()
    discovery_policy = client.post(
        "/api/v1/admin/crawler/discovery-policy-versions",
        json={
            "name": f"Contract discovery {suffix}",
            "strategies": [discovery_strategy_key],
        },
    )
    discovery_policy.raise_for_status()
    discovery_policy_data = discovery_policy.json()["data"]
    expected_discovery_policy = {
        "id": discovery_policy_data["id"],
        "name": discovery_policy_data["name"],
        "version": discovery_policy_data["version"],
        "source": "catalog",
        "strategies": discovery_policy_data["strategies"],
        "sources": discovery_policy_data["strategies"],
        "configuration": discovery_policy_data["configuration"],
    }
    client.post(
        "/api/v1/admin/crawler/discovery-policy-versions/"
        f"{discovery_policy.json()['data']['id']}/publish"
    ).raise_for_status()
    extraction_policy = client.post(
        "/api/v1/admin/crawler/extraction-policy-versions",
        json={
            "name": f"Contract extraction {suffix}",
            "strategies": ["xpath"],
        },
    )
    extraction_policy.raise_for_status()
    extraction_policy_data = extraction_policy.json()["data"]
    expected_extraction_policy = {
        "id": extraction_policy_data["id"],
        "name": extraction_policy_data["name"],
        "version": extraction_policy_data["version"],
        "source": "catalog",
        "strategies": extraction_policy_data["strategies"],
        "configuration": extraction_policy_data["configuration"],
    }
    client.post(
        "/api/v1/admin/crawler/extraction-policy-versions/"
        f"{extraction_policy.json()['data']['id']}/publish"
    ).raise_for_status()
    model = client.post(
        "/api/v1/admin/crawler/onboarding-execution-model-versions",
        json={
            "name": f"Contract model {suffix}",
            "discovery_policy_version_id": discovery_policy.json()["data"]["id"],
            "extraction_policy_version_id": extraction_policy.json()["data"]["id"],
        },
    )
    model.raise_for_status()
    client.post(
        "/api/v1/admin/crawler/onboarding-execution-model-versions/"
        f"{model.json()['data']['id']}/publish"
    ).raise_for_status()

    plan = client.put(
        f"/api/v1/admin/crawler/crawl-agencies/{agency['id']}/onboarding-plan",
        json={
            "name": f"Contract execution {suffix}",
            "conduction": "automated",
            "execution_model_version_id": model.json()["data"]["id"],
        },
    )
    plan.raise_for_status()
    confirmation = client.post(
        f"/api/v1/admin/crawler/crawl-agencies/{agency['id']}/onboarding-plan/confirm"
    )
    confirmation.raise_for_status()
    execution = confirmation.json()["data"]
    assert execution["state"] == "queued"
    assert execution["operations"] == []

    profile_generator = ContractProfileGenerator()
    validation_executor = ContractValidationExecutor()
    production_executor = ContractProductionExecutor()
    worker = CrawlerWorker(
        store=PostgresOperationStore(config),
        discoverer=ContractDiscoverer(),
        profile_generator=profile_generator,
        validation_executor=validation_executor,
        production_crawl_executor=production_executor,
        worker_key=f"onboarding-contract-worker-{suffix}",
        version="onboarding-contract-test",
    )

    for expected_type in ("discovery", "profile_generation", "profile_validation"):
        _reconcile_onboarding()
        current = client.get(
            f"/api/v1/admin/crawler/onboarding-executions/{execution['id']}"
        )
        current.raise_for_status()
        matching = [
            operation
            for operation in current.json()["data"]["operations"]
            if operation["type"] == expected_type
        ]
        assert len(matching) == 1
        _run_until_operation_succeeds(worker, client, matching[0]["id"])

    _reconcile_onboarding()
    completed = client.get(
        f"/api/v1/admin/crawler/onboarding-executions/{execution['id']}"
    )
    completed.raise_for_status()
    data = completed.json()["data"]
    assert data["state"] == "awaiting_approval"
    assert data["current_step"] == "approval"
    assert data["next_action"] == "decide_onboarding"
    assert [operation["type"] for operation in data["operations"]] == [
        "discovery",
        "profile_generation",
        "profile_validation",
    ]
    assert expected_extraction_policy in profile_generator.seen_policies
    assert expected_extraction_policy in validation_executor.seen_policies

    generation_operation = next(
        operation
        for operation in data["operations"]
        if operation["type"] == "profile_generation"
    )
    with psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
    ) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT strategies, parameters->'extraction_policy'
                FROM crawler.extraction_profiles
                WHERE created_by_operation_id = %s
                """,
                (generation_operation["id"],),
            )
            persisted_strategies, persisted_policy = cursor.fetchone()
    assert persisted_strategies == expected_extraction_policy["strategies"]
    assert persisted_policy == expected_extraction_policy

    approval = client.post(
        f"/api/v1/admin/crawler/onboarding-executions/{execution['id']}/approve"
    )
    approval.raise_for_status()
    approval_data = approval.json()["data"]
    assert approval_data["state"] == "running"
    assert approval_data["current_step"] == "first_production"
    production_operation = next(
        operation
        for operation in approval_data["operations"]
        if operation["type"] == "production_crawl"
    )
    _run_until_operation_succeeds(
        worker,
        client,
        production_operation["id"],
    )
    _reconcile_onboarding()

    finished = client.get(
        f"/api/v1/admin/crawler/onboarding-executions/{execution['id']}"
    )
    finished.raise_for_status()
    finished_data = finished.json()["data"]
    assert finished_data["state"] == "completed"
    assert finished_data["current_step"] == "quality_gate"
    assert finished_data["first_production"]["publication_state"] == "published"
    assert finished_data["first_production"]["quality_verdict"] == "approved"
    assert [operation["type"] for operation in finished_data["operations"]] == [
        "discovery",
        "profile_generation",
        "profile_validation",
        "production_crawl",
    ]
    assert production_executor.seen_plans[-1]["discovery_policy"] == (
        expected_discovery_policy
    )
    assert production_executor.seen_plans[-1]["extraction_policy"] == (
        expected_extraction_policy
    )


def _run_until_operation_succeeds(
    worker: CrawlerWorker,
    client: httpx.Client,
    operation_id: int,
) -> dict[str, Any]:
    for _ in range(100):
        response = client.get(f"/api/v1/admin/crawler/operations/{operation_id}")
        response.raise_for_status()
        operation = response.json()["data"]
        if operation["state"] == "succeeded":
            return operation
        if operation["state"] in {"failed", "cancelled"}:
            raise AssertionError(
                f"operation {operation_id} ended as {operation['state']}"
            )
        if worker.run_once() is not True:
            break
    raise AssertionError(f"operation {operation_id} did not succeed")


def _reconcile_onboarding() -> None:
    command = shlex.split(os.environ["LARAVEL_CONTRACT_ARTISAN"])
    result = subprocess.run(
        [*command, "crawler:reconcile-onboarding-executions"],
        cwd=os.environ["LARAVEL_CONTRACT_ARTISAN_CWD"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"Laravel onboarding coordinator failed: {result.stderr.strip()}"
        )
