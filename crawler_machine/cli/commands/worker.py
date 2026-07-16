from __future__ import annotations

import socket
import time

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import load_env_file, setup_logging
from crawler_machine.discoverer import URLDiscoverer
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.worker.postgres_store import PostgresOperationStore
from crawler_machine.worker.runner import CrawlerWorker


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
) -> None:
    """Executa o worker durável que reivindica operações no Postgres."""
    load_env_file()
    setup_logging()
    config = PostgresConfig.from_env()
    if config is None:
        raise typer.BadParameter("Defina todas as variáveis DB_* para executar o worker.")

    runner = CrawlerWorker(
        store=PostgresOperationStore(config),
        discoverer=URLDiscoverer(),
        worker_key=worker_key,
        version=version,
    )

    while True:
        processed = runner.run_once()
        if once:
            return
        if not processed:
            time.sleep(poll_seconds)
