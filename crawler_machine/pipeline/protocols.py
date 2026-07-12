from __future__ import annotations

from typing import Any, Callable, Protocol


class Discoverer(Protocol):
    async def discover(self, base_url: str) -> list[str]: ...


class SchemaGenerator(Protocol):
    async def generate(self, sample_url: str) -> dict[str, Any]: ...


class Crawler(Protocol):
    async def crawl(
        self, urls: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...


class Sink(Protocol):
    """Protocolo para persistência de execuções do crawler."""

    def start_run(self, source_name: str) -> int: ...
    def fail_run(self, run_id: int, error_message: str) -> None: ...
    def save_run(
        self,
        source_name: str,
        raw_properties: list[dict[str, Any]],
        normalized_properties: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> int: ...
    def start_discovery_run(self, source_name: str) -> int: ...
    def save_discovery_run(self, source_name: str, urls: list[str]) -> int: ...
    def fail_discovery_run(self, run_id: int, error_message: str) -> None: ...
    def load_latest_discovery(self, source_name: str) -> list[str] | None: ...
    def link_discovery_run(
        self, discovery_run_id: int, crawler_run_id: int
    ) -> None: ...
    def start_schema_run(self, source_name: str) -> int: ...
    def save_schema_run(
        self,
        source_name: str,
        schema_data: dict[str, Any],
        schema_type: str,
        sample_url: str,
        fields_snapshot: list[dict[str, Any]],
    ) -> int: ...
    def fail_schema_run(self, run_id: int, error_message: str) -> None: ...
    def load_latest_schema(self, source_name: str) -> dict[str, Any] | None: ...
    def link_schema_run(
        self, schema_run_id: int, crawler_run_id: int
    ) -> None: ...
    def catalog_repository(self) -> "CatalogRepository": ...


CrawlerFactory = Callable[[dict[str, Any]], Crawler]
ProgressCallback = Callable[[str, int, str], None]
