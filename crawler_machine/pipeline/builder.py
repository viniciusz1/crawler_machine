from __future__ import annotations

import logging
from typing import Any

from tqdm import tqdm

from crawler_machine.config import DomainConfig
from crawler_machine.discoverer import URLDiscoverer
from crawler_machine.extraction.factory import build_crawl_engine
from crawler_machine.output import OutputPath
from crawler_machine.pipeline.core import Pipeline
from crawler_machine.pipeline.protocols import ProgressCallback
from crawler_machine.schema_generator import SchemaGenerator
from crawler_machine.sink import RunStore


def _make_progress_callback(
    progress_bar: tqdm[Any] | None,
) -> ProgressCallback | None:
    if progress_bar is None:
        return None

    def callback(step: str, percent: int, message: str) -> None:
        logging.info("[%3d%%] [%s] %s", percent, step, message)
        progress_bar.set_description(f"{step}: {message}")
        progress_bar.n = percent
        progress_bar.refresh()

    return callback


def build_pipeline(
    config: DomainConfig,
    output: OutputPath,
    source_name: str | None = None,
    sink: RunStore | None = None,
    progress_callback: ProgressCallback | None = None,
    progress_bar: tqdm[Any] | None = None,
    enable_llm_fallback: bool | None = None,
    verbose: bool = False,
) -> Pipeline:
    """Constrói um Pipeline com a configuração e adapters padrão.

    Centraliza a montagem do grafo de objetos para que os pontos de entrada
    (CLI e batch) não dupliquem a lógica de wiring.

    ``progress_bar`` é um atalho para a CLI: monta um callback que loga e
    atualiza a barra tqdm. Se ``progress_callback`` também for passado,
    ele tem precedência.
    """
    effective_callback = progress_callback or _make_progress_callback(progress_bar)
    catalog_repository = sink.catalog_repository() if sink is not None else None

    def _crawler_factory(schema: dict[str, Any]) -> Any:
        return build_crawl_engine(
            config=config,
            schema=schema,
            enable_llm_fallback=enable_llm_fallback,
        )

    return Pipeline(
        config=config,
        output=output,
        discoverer=URLDiscoverer(
            max_urls=config.discovery.max_urls,
            listing_patterns=config.discovery.listing_patterns,
        ),
        schema_generator=SchemaGenerator(
            llm_config=config.llm,
            fields=config.fields,
            verbose=verbose,
        ),
        crawler_factory=_crawler_factory,
        progress_callback=effective_callback,
        sink=sink,
        source_name=source_name,
        catalog_repository=catalog_repository,
    )
