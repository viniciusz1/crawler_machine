from __future__ import annotations

import os
import uuid

import httpx
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
    def discover_sync(self, base_url: str) -> list[str]:
        return [f"{base_url.rstrip('/')}/imovel/contract-1"]


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
    assert worker.run_once() is True

    completed_response = client.get(
        f"/api/v1/admin/crawler/operations/{operation['id']}"
    )
    completed_response.raise_for_status()
    completed = completed_response.json()["data"]
    assert completed["state"] == "succeeded"
    urls_response = client.get(
        f"/api/v1/admin/crawler/discovery-snapshots/{completed['discovery_snapshot_id']}/urls"
    )
    urls_response.raise_for_status()
    assert urls_response.json()["data"][0]["url"].endswith("/imovel/contract-1")
