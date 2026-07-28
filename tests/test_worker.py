from __future__ import annotations

from dataclasses import dataclass, field

from crawler_machine.worker.runner import CrawlerWorker
from crawler_machine.worker.store import ClaimedOperation


@dataclass
class FakeOperationStore:
    operation: ClaimedOperation | None
    progress: list[tuple[int, str, int, int, int, str]] = field(default_factory=list)
    completed: list[tuple[int, list[str]]] = field(default_factory=list)
    completed_suggestions: list[tuple[int, str | None]] = field(default_factory=list)
    completed_profiles: list[tuple[int, dict]] = field(default_factory=list)
    completed_validations: list[tuple[int, dict]] = field(default_factory=list)
    completed_production_crawls: list[tuple[int, dict]] = field(default_factory=list)
    completed_prospecting: list[tuple[int, list[dict]]] = field(default_factory=list)
    cancellation_requests: set[int] = field(default_factory=set)
    cancelled: list[int] = field(default_factory=list)

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

    def complete_sample_suggestion(
        self, operation_id: int, worker_key: str, sample_url: str | None
    ) -> None:
        self.completed_suggestions.append((operation_id, sample_url))

    def complete_profile(
        self, operation_id: int, worker_key: str, profile: dict
    ) -> None:
        self.completed_profiles.append((operation_id, profile))

    def complete_validation(
        self, operation_id: int, worker_key: str, report: dict
    ) -> None:
        self.completed_validations.append((operation_id, report))

    def complete_production_crawl(
        self, operation_id: int, worker_key: str, result: dict
    ) -> None:
        self.completed_production_crawls.append((operation_id, result))

    def known_prospect_domains(self) -> set[str]:
        return {"known.example.com"}

    def complete_prospecting(
        self, operation_id: int, worker_key: str, prospects: list[dict]
    ) -> None:
        self.completed_prospecting.append((operation_id, prospects))

    def cancellation_requested(self, operation_id: int, worker_key: str) -> bool:
        return operation_id in self.cancellation_requests

    def cancel(self, operation_id: int, worker_key: str) -> None:
        self.cancelled.append(operation_id)

    def fail(self, operation_id: int, worker_key: str, code: str, message: str) -> None:
        raise AssertionError(f"unexpected failure: {code} {message}")


class FakeDiscoverer:
    def discover_sync(self, base_url: str) -> list[str]:
        assert base_url == "https://agency.example.com/imoveis"
        return [
            "https://agency.example.com/imovel/1",
            "https://agency.example.com/imovel/2",
        ]


class FakeSampleFinder:
    def find(self, base_url: str) -> str | None:
        assert base_url == "https://agency.example.com"
        return "https://agency.example.com/imovel/confirmed-candidate"


class FakeProfileGenerator:
    def __init__(self) -> None:
        self.policies: list[dict | None] = []

    def generate(
        self,
        sample_url: str,
        fields: list[dict],
        extraction_policy: dict | None = None,
    ) -> dict:
        assert sample_url == "https://agency.example.com/imovel/confirmed"
        assert fields[0]["name"] == "title"
        self.policies.append(extraction_policy)
        return {
            "schemas": {"xpath": {"fields": []}, "css": {"fields": []}},
            "strategies": (
                list(extraction_policy["strategies"])
                if extraction_policy is not None
                else ["xpath", "css"]
            ),
            "fields": fields,
            "parameters": {"generated_by": "fake"},
        }


class FakeValidationExecutor:
    def run(self, plan: dict) -> dict:
        assert len(plan["urls"]) == 2
        return {
            "sampled_url_count": 2,
            "valid_record_count": 2,
            "valid_ratio": 1.0,
            "required_field_coverage": {"title": 1.0},
            "blocking_failures": [],
            "warnings": [],
            "eligible": True,
            "records": [],
        }


class FakeProductionCrawlExecutor:
    def run(self, plan: dict, should_cancel) -> dict:
        assert plan["crawl_agency_id"] == 42
        return {
            "technical_state": "succeeded",
            "result_kind": "full",
            "publishable": True,
            "discovery": {"mode": "existing", "snapshot_id": 5},
            "raw_properties": [],
            "market_properties": [],
            "rejected_properties": [],
            "errors": [],
            "artifacts": [],
            "technical_logs": [],
        }


class FakeProspectingExecutor:
    def run(self, plan: dict, known_domains: set[str]) -> list[dict]:
        assert plan["city"] == "Joinville"
        assert known_domains == {"known.example.com"}
        return [{"root_domain": "new.example.com", "automatic_classification": "candidate"}]


def test_worker_persists_prospecting_results_from_gateway_executor() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=13,
            type="prospecting",
            crawl_agency_id=None,
            plan={"city": "Joinville", "state": "SC"},
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        prospecting_executor=FakeProspectingExecutor(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed_prospecting == [
        (13, [{"root_domain": "new.example.com", "automatic_classification": "candidate"}])
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


def test_worker_suggests_sample_only_from_home_finder() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=8,
            type="sample_url_suggestion",
            crawl_agency_id=42,
            plan={"base_url": "https://agency.example.com"},
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        sample_finder=FakeSampleFinder(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed_suggestions == [
        (8, "https://agency.example.com/imovel/confirmed-candidate")
    ]


def test_worker_persists_immutable_candidate_profile() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=9,
            type="profile_generation",
            crawl_agency_id=42,
            plan={
                "sample_url": "https://agency.example.com/imovel/confirmed",
                "sample_url_confirmed": True,
                "contract_fields": [
                    {"name": "title", "type": "string", "required": True}
                ],
            },
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        profile_generator=FakeProfileGenerator(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed_profiles[0][0] == 9
    assert store.completed_profiles[0][1]["strategies"] == ["xpath", "css"]


def test_worker_passes_fixed_extraction_policy_to_profile_generation() -> None:
    policy = {
        "id": "019c-fixed-policy",
        "version": 3,
        "source": "catalog",
        "strategies": ["css", "llm_full_html"],
        "configuration": {},
    }
    store = FakeOperationStore(
        ClaimedOperation(
            id=14,
            type="profile_generation",
            crawl_agency_id=42,
            plan={
                "sample_url": "https://agency.example.com/imovel/confirmed",
                "sample_url_confirmed": True,
                "contract_fields": [
                    {"name": "title", "type": "string", "required": True}
                ],
                "extraction_policy": policy,
            },
        )
    )
    generator = FakeProfileGenerator()
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        profile_generator=generator,
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert generator.policies == [policy]
    assert store.completed_profiles[0][1]["strategies"] == [
        "css",
        "llm_full_html",
    ]


def test_worker_persists_profile_validation_report() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=10,
            type="profile_validation",
            crawl_agency_id=42,
            plan={
                "urls": [
                    "https://agency.example.com/property/1",
                    "https://agency.example.com/property/2",
                ]
            },
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        validation_executor=FakeValidationExecutor(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed_validations[0][0] == 10
    assert store.completed_validations[0][1]["eligible"] is True


def test_worker_persists_production_crawl_without_publishing_it() -> None:
    store = FakeOperationStore(
        ClaimedOperation(
            id=11,
            type="production_crawl",
            crawl_agency_id=42,
            plan={"crawl_agency_id": 42},
        )
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        production_crawl_executor=FakeProductionCrawlExecutor(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.completed_production_crawls[0][0] == 11
    assert store.completed_production_crawls[0][1]["publishable"] is True


def test_worker_honors_cancellation_before_starting_expensive_work() -> None:
    store = FakeOperationStore(
        ClaimedOperation(id=12, type="discovery", crawl_agency_id=42, plan={"base_url": "https://agency.example.com"}),
        cancellation_requests={12},
    )
    worker = CrawlerWorker(
        store=store,
        discoverer=FakeDiscoverer(),
        worker_key="worker-a",
        version="1.0.0",
    )

    assert worker.run_once() is True
    assert store.cancelled == [12]
    assert store.completed == []
