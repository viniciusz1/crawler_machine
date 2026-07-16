from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ClaimedOperation:
    id: int
    type: str
    crawl_agency_id: int
    plan: dict[str, Any]


class OperationStore(Protocol):
    def register_worker(
        self, worker_key: str, version: str, capacity: dict[str, int]
    ) -> None: ...

    def claim(
        self, worker_key: str, supported_types: tuple[str, ...]
    ) -> ClaimedOperation | None: ...

    def heartbeat(
        self,
        operation_id: int,
        worker_key: str,
        stage: str,
        percentage: int,
        processed: int,
        total: int,
        message: str,
    ) -> None: ...

    def complete_discovery(
        self, operation_id: int, worker_key: str, urls: list[str]
    ) -> None: ...

    def fail(
        self, operation_id: int, worker_key: str, code: str, message: str
    ) -> None: ...
