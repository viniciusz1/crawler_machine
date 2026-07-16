from __future__ import annotations

from dataclasses import dataclass, field

from crawler_machine.worker.runner import CrawlerWorker
from crawler_machine.worker.store import ClaimedOperation


@dataclass
class FakeOperationStore:
    operation: ClaimedOperation | None
    progress: list[tuple[int, str, int, int, int, str]] = field(default_factory=list)
    completed: list[tuple[int, list[str]]] = field(default_factory=list)

    def register_worker(self, worker_key: str, version: str, capacity: dict[str, int]) -> None:
        self.registration = (worker_key, version, capacity)

    def claim(self, worker_key: str, supported_types: tuple[str, ...]) -> ClaimedOperation | None:
        operation, self.operation = self.operation, None
        return operation

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
        self.progress.append((operation_id, stage, percentage, processed, total, message))

    def complete_discovery(self, operation_id: int, worker_key: str, urls: list[str]) -> None:
        self.completed.append((operation_id, urls))

    def fail(self, operation_id: int, worker_key: str, code: str, message: str) -> None:
        raise AssertionError(f"unexpected failure: {code} {message}")


class FakeDiscoverer:
    def discover_sync(self, base_url: str) -> list[str]:
        assert base_url == "https://agency.example.com/imoveis"
        return [
            "https://agency.example.com/imovel/1",
            "https://agency.example.com/imovel/2",
        ]


def test_worker_claims_and_completes_discovery_operation() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=7,
            type="discovery",
            crawl_agency_id=42,
            plan={"base_url": "https://agency.example.com/imoveis"},
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed == [
        (
            7,
            [
                "https://agency.example.com/imovel/1",
                "https://agency.example.com/imovel/2",
            ],
        )
    ]
    assert store.progress[-1][1:5] == ("discovery", 90, 2, 2)
