from __future__ import annotations

from typing import Protocol

from crawler_machine.worker.store import OperationStore


class SynchronousDiscoverer(Protocol):
    def discover_sync(self, base_url: str) -> list[str]: ...


class CrawlerWorker:
    SUPPORTED_TYPES = ("discovery",)

    def __init__(
        self,
        store: OperationStore,
        discoverer: SynchronousDiscoverer,
        worker_key: str,
        version: str,
    ) -> None:
        self._store = store
        self._discoverer = discoverer
        self._worker_key = worker_key
        self._store.register_worker(worker_key, version, {"concurrency": 1})

    def run_once(self) -> bool:
        operation = self._store.claim(self._worker_key, self.SUPPORTED_TYPES)
        if operation is None:
            return False

        try:
            self._store.heartbeat(
                operation.id,
                self._worker_key,
                "discovery",
                10,
                0,
                0,
                "Starting URL discovery",
            )
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
            self._store.complete_discovery(
                operation.id, self._worker_key, urls
            )
        except Exception as exception:
            self._store.fail(
                operation.id,
                self._worker_key,
                "discovery_failed",
                str(exception),
            )

        return True
