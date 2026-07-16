from __future__ import annotations

from typing import Any, Protocol

from crawler_machine.worker.store import OperationStore


class SynchronousDiscoverer(Protocol):
    def discover_sync(self, base_url: str) -> list[str]: ...


class SampleFinder(Protocol):
    def find(self, base_url: str) -> str | None: ...


class ProfileGenerator(Protocol):
    def generate(self, sample_url: str, fields: list[dict[str, Any]]) -> dict[str, Any]: ...


class ValidationExecutor(Protocol):
    def run(self, plan: dict[str, Any]) -> dict[str, Any]: ...


class CrawlerWorker:
    def __init__(
        self,
        store: OperationStore,
        discoverer: SynchronousDiscoverer,
        worker_key: str,
        version: str,
        sample_finder: SampleFinder | None = None,
        profile_generator: ProfileGenerator | None = None,
        validation_executor: ValidationExecutor | None = None,
    ) -> None:
        self._store = store
        self._discoverer = discoverer
        self._worker_key = worker_key
        self._sample_finder = sample_finder
        self._profile_generator = profile_generator
        self._validation_executor = validation_executor
        self._supported_types = ("discovery",) + (
            ("sample_url_suggestion",) if sample_finder is not None else ()
        ) + (("profile_generation",) if profile_generator is not None else ()) + (
            ("profile_validation",) if validation_executor is not None else ()
        )
        self._store.register_worker(worker_key, version, {"concurrency": 1})

    def run_once(self) -> bool:
        operation = self._store.claim(self._worker_key, self._supported_types)
        if operation is None:
            return False

        try:
            self._store.heartbeat(
                operation.id,
                self._worker_key,
                operation.type,
                10,
                0,
                0,
                "Starting URL discovery",
            )
            if operation.type == "discovery":
                urls = self._discoverer.discover_sync(str(operation.plan["base_url"]))
                self._store.heartbeat(
                    operation.id,
                    self._worker_key,
                    "discovery",
                    90,
                    len(urls),
                    len(urls),
                    "Discovery completed; persisting snapshot",
                )
                self._store.complete_discovery(operation.id, self._worker_key, urls)
            elif operation.type == "sample_url_suggestion" and self._sample_finder:
                sample_url = self._sample_finder.find(str(operation.plan["base_url"]))
                self._store.complete_sample_suggestion(
                    operation.id, self._worker_key, sample_url
                )
            elif operation.type == "profile_generation" and self._profile_generator:
                if operation.plan.get("sample_url_confirmed") is not True:
                    raise RuntimeError("sample URL was not confirmed by an operator")
                profile = self._profile_generator.generate(
                    str(operation.plan["sample_url"]),
                    list(operation.plan["contract_fields"]),
                )
                self._store.complete_profile(operation.id, self._worker_key, profile)
            elif operation.type == "profile_validation" and self._validation_executor:
                report = self._validation_executor.run(operation.plan)
                self._store.complete_validation(operation.id, self._worker_key, report)
            else:
                raise RuntimeError(f"unsupported operation type: {operation.type}")
        except Exception as exception:
            self._store.fail(
                operation.id,
                self._worker_key,
                "discovery_failed",
                str(exception),
            )

        return True
