from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone
from time import perf_counter
from typing import Any, Protocol

from crawler_machine.worker.store import OperationStore

logger = logging.getLogger(__name__)


class SynchronousDiscoverer(Protocol):
    def discover_sync(self, base_url: str) -> list[str]: ...


class SampleFinder(Protocol):
    def find(self, base_url: str) -> str | None: ...


class ProfileGenerator(Protocol):
    def generate(
        self,
        sample_url: str,
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...


class ValidationExecutor(Protocol):
    def run(self, plan: dict[str, Any]) -> dict[str, Any]: ...


class ProductionCrawlExecutor(Protocol):
    def run(
        self, plan: dict[str, Any], should_cancel: Callable[[], bool]
    ) -> dict[str, Any]: ...


class ProspectingExecutor(Protocol):
    def run(
        self, plan: dict[str, Any], known_domains: set[str]
    ) -> list[dict[str, Any]]: ...


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
        production_crawl_executor: ProductionCrawlExecutor | None = None,
        prospecting_executor: ProspectingExecutor | None = None,
    ) -> None:
        self._store = store
        self._discoverer = discoverer
        self._worker_key = worker_key
        self._sample_finder = sample_finder
        self._profile_generator = profile_generator
        self._validation_executor = validation_executor
        self._production_crawl_executor = production_crawl_executor
        self._prospecting_executor = prospecting_executor
        self._supported_types = ("discovery",) + (
            ("sample_url_suggestion",) if sample_finder is not None else ()
        ) + (("profile_generation",) if profile_generator is not None else ()) + (
            ("profile_validation",) if validation_executor is not None else ()
        ) + (
            ("production_crawl",) if production_crawl_executor is not None else ()
        ) + (
            ("prospecting",) if prospecting_executor is not None else ()
        )
        self._store.register_worker(worker_key, version, {"concurrency": 1})

    def run_once(self) -> bool:
        operation = self._store.claim(self._worker_key, self._supported_types)
        if operation is None:
            return False

        started_at = datetime.now(timezone.utc)
        started_clock = perf_counter()
        status = "running"
        logger.info(
            "crawler_operation_started operation_id=%s operation_type=%s "
            "crawl_agency_id=%s worker_key=%s started_at=%s",
            operation.id,
            operation.type,
            operation.crawl_agency_id,
            self._worker_key,
            started_at.isoformat(),
        )

        try:
            if self._store.cancellation_requested(operation.id, self._worker_key):
                self._store.cancel(operation.id, self._worker_key)
                status = "cancelled"
                return True

            self._store.heartbeat(
                operation.id,
                self._worker_key,
                operation.type,
                10,
                0,
                0,
                f"Starting {operation.type}",
            )
            if operation.type == "discovery":
                policy = operation.plan.get("discovery_policy")
                urls = (
                    self._discoverer.discover_sync(str(operation.plan["base_url"]), policy)
                    if isinstance(policy, dict)
                    else self._discoverer.discover_sync(str(operation.plan["base_url"]))
                )
                if self._cancel_if_requested(operation.id):
                    status = "cancelled"
                    return True
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
                status = "succeeded"
            elif operation.type == "sample_url_suggestion" and self._sample_finder:
                sample_url = self._sample_finder.find(str(operation.plan["base_url"]))
                if self._cancel_if_requested(operation.id):
                    status = "cancelled"
                    return True
                self._store.complete_sample_suggestion(
                    operation.id, self._worker_key, sample_url
                )
                status = "succeeded"
            elif operation.type == "profile_generation" and self._profile_generator:
                if operation.plan.get("sample_url_confirmed") is not True:
                    raise RuntimeError("sample URL was not confirmed by an operator")
                extraction_policy = operation.plan.get("extraction_policy")
                if isinstance(extraction_policy, dict):
                    profile = self._profile_generator.generate(
                        str(operation.plan["sample_url"]),
                        list(operation.plan["contract_fields"]),
                        extraction_policy,
                    )
                else:
                    profile = self._profile_generator.generate(
                        str(operation.plan["sample_url"]),
                        list(operation.plan["contract_fields"]),
                    )
                if self._cancel_if_requested(operation.id):
                    status = "cancelled"
                    return True
                self._store.complete_profile(operation.id, self._worker_key, profile)
                status = "succeeded"
            elif operation.type == "profile_validation" and self._validation_executor:
                report = self._validation_executor.run(operation.plan)
                if self._cancel_if_requested(operation.id):
                    status = "cancelled"
                    return True
                self._store.complete_validation(operation.id, self._worker_key, report)
                status = "succeeded"
            elif operation.type == "production_crawl" and self._production_crawl_executor:
                result = self._production_crawl_executor.run(
                    operation.plan,
                    lambda: self._store.cancellation_requested(
                        operation.id, self._worker_key
                    ),
                )
                self._store.complete_production_crawl(
                    operation.id, self._worker_key, result
                )
                status = (
                    "cancelled"
                    if result.get("technical_state") == "cancelled"
                    else "failed"
                    if result.get("technical_state") == "failed"
                    else "succeeded"
                )
            elif operation.type == "prospecting" and self._prospecting_executor:
                prospects = self._prospecting_executor.run(
                    operation.plan, self._store.known_prospect_domains()
                )
                if self._cancel_if_requested(operation.id):
                    status = "cancelled"
                    return True
                self._store.complete_prospecting(
                    operation.id, self._worker_key, prospects
                )
                status = "succeeded"
            else:
                raise RuntimeError(f"unsupported operation type: {operation.type}")
        except Exception as exception:
            if self._cancel_if_requested(operation.id):
                status = "cancelled"
                logger.warning(
                    "crawler_operation_cancelled operation_id=%s operation_type=%s "
                    "after_error=%s",
                    operation.id,
                    operation.type,
                    str(exception),
                )
                return True
            status = "failed"
            logger.exception(
                "crawler_operation_failed operation_id=%s operation_type=%s",
                operation.id,
                operation.type,
            )
            self._store.fail(
                operation.id,
                self._worker_key,
                f"{operation.type}_failed",
                str(exception),
            )
        finally:
            self._log_operation_finished(
                operation.id,
                operation.type,
                operation.crawl_agency_id,
                started_at,
                started_clock,
                status,
            )

        return True

    def _log_operation_finished(
        self,
        operation_id: int,
        operation_type: str,
        crawl_agency_id: int | None,
        started_at: datetime,
        started_clock: float,
        status: str,
    ) -> None:
        finished_at = datetime.now(timezone.utc)
        logger.info(
            "crawler_operation_finished operation_id=%s operation_type=%s "
            "crawl_agency_id=%s worker_key=%s status=%s started_at=%s "
            "finished_at=%s duration_seconds=%.3f",
            operation_id,
            operation_type,
            crawl_agency_id,
            self._worker_key,
            status,
            started_at.isoformat(),
            finished_at.isoformat(),
            perf_counter() - started_clock,
        )

    def _cancel_if_requested(self, operation_id: int) -> bool:
        if not self._store.cancellation_requested(operation_id, self._worker_key):
            return False
        self._store.cancel(operation_id, self._worker_key)
        return True
