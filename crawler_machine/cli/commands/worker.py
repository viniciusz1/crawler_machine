from __future__ import annotations

import socket
import time
from pathlib import Path

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import load_config, load_env_file, setup_logging
from crawler_machine.discoverer import URLDiscoverer
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.adapters import (
    ConfiguredProfileExtractor,
    ExtractionProfileGenerator,
    HomeSampleFinderAdapter,
)
from crawler_machine.worker.postgres_store import PostgresOperationStore
from crawler_machine.worker.production import ProductionCrawlExecutor
from crawler_machine.worker.runner import CrawlerWorker
from crawler_machine.worker.validation import ProfileValidationExecutor


@app.command()
def worker(
    worker_key: str = typer.Option(
        socket.gethostname(), "--worker-key", help="Identidade estável do worker"
    ),
    version: str = typer.Option("dev", "--version", help="Versão implantada"),
    poll_seconds: float = typer.Option(
        3.0, "--poll-seconds", min=0.1, help="Intervalo quando a fila está vazia"
    ),
    once: bool = typer.Option(False, "--once", help="Processa no máximo uma operação"),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Configuração de LLM do worker"
    ),
) -> None:
    """Executa o worker durável que reivindica operações no Postgres."""
    load_env_file()
    setup_logging()
    config = PostgresConfig.from_env()
    if config is None:
        raise typer.BadParameter("Defina todas as variáveis DB_* para executar o worker.")
    domain_config = load_config(config_path)

    operation_store = PostgresOperationStore(config)
    discoverer = URLDiscoverer()
    profile_extractor = ConfiguredProfileExtractor(domain_config)
    runner = CrawlerWorker(
        store=operation_store,
        discoverer=discoverer,
        worker_key=worker_key,
        version=version,
        sample_finder=HomeSampleFinderAdapter(),
        profile_generator=ExtractionProfileGenerator(domain_config.llm),
        validation_executor=ProfileValidationExecutor(
            profile_extractor
        ),
        production_crawl_executor=ProductionCrawlExecutor(
            discoverer=discoverer,
            extractor=profile_extractor,
        ),
    )

    while True:
        processed = runner.run_once()
        if once:
            return
        if not processed:
            time.sleep(poll_seconds)
