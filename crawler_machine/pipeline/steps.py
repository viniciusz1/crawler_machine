from __future__ import annotations

from typing import Any

from crawler_machine.config import DomainConfig
from crawler_machine.extermination.exterminator import Exterminator, RejectedRecord
from crawler_machine.pipeline.discovery_cache import DiscoveryCache
from crawler_machine.pipeline.normalizer_factory import NormalizerFactory
from crawler_machine.pipeline.protocols import (
    CrawlerFactory,
    Discoverer,
    ProgressCallback,
    SchemaGenerator,
    Sink,
)
from crawler_machine.pipeline.schema_cache import SchemaCache
from crawler_machine.pipeline.state import ExecutionState


async def discover_urls(
    source_name: str,
    base_url: str,
    regenerate: bool,
    discoverer: Discoverer,
    sink: Sink | None,
    report: ProgressCallback | None,
) -> tuple[list[str], int | None]:
    cache = DiscoveryCache(sink)
    cached = await cache.load(source_name, regenerate)
    if cached is not None:
        _report(report, "discovery", 25, f"{len(cached)} URLs reutilizadas do cache")
        return cached, None

    _report(report, "discovery", 0, "Iniciando descoberta de URLs...")
    urls = await discoverer.discover(base_url)
    _report(report, "discovery", 25, f"{len(urls)} URLs descobertas")

    discovery_run_id = await cache.save(source_name, urls)
    return urls, discovery_run_id


async def build_schema(
    source_name: str,
    sample_url: str | None,
    regenerate: bool,
    schema_generator: SchemaGenerator,
    sink: Sink | None,
    report: ProgressCallback | None,
) -> tuple[dict[str, Any], int | None]:
    cache = SchemaCache(sink)
    cached = await cache.load(source_name, regenerate)
    if cached is not None:
        _report(report, "schema", 50, "Schema reutilizado do cache")
        return cached, None

    effective_sample = _require_sample_url(sample_url, sink)
    _report(
        report, "schema", 25, f"Gerando schema a partir de {effective_sample}..."
    )
    schema = await schema_generator.generate(effective_sample)
    _report(report, "schema", 50, "Schema gerado")

    schema_run_id = await cache.save(source_name, schema, effective_sample)
    return schema, schema_run_id


def _require_sample_url(sample_url: str | None, sink: Sink | None) -> str:
    if sample_url is not None:
        return sample_url

    if sink is not None:
        raise ValueError(
            "sample_url é obrigatório quando não há schema cacheado. "
            "Passe --sample-url ou execute com --regenerate-schema."
        )
    raise ValueError(
        "sample_url é obrigatório quando Postgres não está configurado "
        "(sem cache de schema disponível). Configure as variáveis DB_* "
        "ou passe --sample-url."
    )


async def crawl_urls(
    urls: list[str],
    schema: dict[str, Any],
    crawler_factory: CrawlerFactory,
    report: ProgressCallback | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    _report(report, "crawl", 50, f"Iniciando crawling de {len(urls)} URLs...")
    crawler = crawler_factory(schema)
    raw_data, errors = await crawler.crawl(urls)
    _report(
        report,
        "crawl",
        75,
        f"{len(raw_data)} registros extraídos | {len(errors)} erros",
    )
    return raw_data, errors


def exterminate_records(
    raw_data: list[dict[str, Any]], report: ProgressCallback | None
) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
    _report(report, "exterminate", 75, "Exterminando registros inválidos...")
    survivors, rejected = Exterminator().filter(raw_data)
    _report(
        report,
        "exterminate",
        80,
        f"{len(survivors)} registros sobreviveram | {len(rejected)} eliminados",
    )
    return survivors, rejected


def normalize_records(
    survivors: list[dict[str, Any]],
    config: DomainConfig,
    sink: Sink | None,
    report: ProgressCallback | None,
    catalog_repository: "CatalogRepository" | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    _report(report, "normalize", 80, "Normalizando dados...")
    normalizer = NormalizerFactory(
        config, catalog_repository=catalog_repository
    ).build()
    return normalizer.normalize_many(survivors)


def make_empty_state() -> ExecutionState:
    return ExecutionState(
        urls=[],
        schema={},
        raw_data=[],
        errors=[],
        survivors=[],
        rejected=[],
        normalized=[],
        quality_report={},
    )


def _report(
    callback: ProgressCallback | None,
    step: str,
    percent: int,
    message: str,
) -> None:
    if callback is not None:
        callback(step, percent, message)
