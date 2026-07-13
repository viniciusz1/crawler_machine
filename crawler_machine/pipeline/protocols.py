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


class CrawlerRunStore(Protocol):
    """Seam para ciclo de vida de crawler_run."""

    def start_run(self, source_name: str) -> int: ...
    def fail_run(self, run_id: int, error_message: str) -> None: ...
    def save_run(
        self,
        source_name: str,
        raw_properties: list[dict[str, Any]],
        normalized_properties: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> int: ...


class DiscoveryRunStore(Protocol):
    """Seam para ciclo de vida de discovery_run."""

    def start_discovery_run(self, source_name: str) -> int: ...
    def save_discovery_run(self, source_name: str, urls: list[str]) -> int: ...
    def fail_discovery_run(self, run_id: int, error_message: str) -> None: ...
    def load_latest_discovery(self, source_name: str) -> list[str] | None: ...


class SchemaRunStore(Protocol):
    """Seam para ciclo de vida de schema_run."""

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


class RunLinker(Protocol):
    """Seam para vincular discovery/schema runs a crawler runs."""

    def link_discovery_run(
        self, discovery_run_id: int, crawler_run_id: int
    ) -> None: ...
    def link_schema_run(
        self, schema_run_id: int, crawler_run_id: int
    ) -> None: ...


class CatalogSource(Protocol):
    """Seam para obter o repositório de catálogo."""

    def catalog_repository(self) -> "CatalogRepository": ...


class Sink(
    CrawlerRunStore,
    DiscoveryRunStore,
    SchemaRunStore,
    RunLinker,
    CatalogSource,
    Protocol,
):
    """Protocolo combinado para persistência de execuções do crawler.

    Mantido para compatibilidade com callers que precisam de todas as
    operações de run. Novo código deve depender das seams menores.
    """


CrawlerFactory = Callable[[dict[str, Any]], Crawler]
ProgressCallback = Callable[[str, int, str], None]
