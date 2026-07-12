from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import load_config, load_sink, make_output, setup_logging
from crawler_machine.discoverer import URLDiscoverer


@app.command()
def discover(
    base_url: str = typer.Argument(..., help="URL base do site da imobiliária"),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Caminho do arquivo de configuração"
    ),
    output_dir: Path = typer.Option(
        Path("output"), "--output", help="Diretório base de saída"
    ),
    source_name: str = typer.Option(
        ..., "--source-name", help="Nome da fonte/imobiliária (slug usado no banco)"
    ),
    save_to_db: bool = typer.Option(
        False, "--save-to-db", help="Persiste os resultados no Postgres"
    ),
) -> None:
    """Descobre URLs do site."""
    setup_logging()
    config = load_config(config_path)
    output = make_output(output_dir, base_url)

    discoverer = URLDiscoverer(
        max_urls=config.discovery.max_urls,
        listing_patterns=config.discovery.listing_patterns,
    )
    urls = discoverer.discover_sync(base_url)

    output.discovered.parent.mkdir(parents=True, exist_ok=True)
    with output.discovered.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "base_url": base_url,
                    "discovered_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(urls),
                },
                "urls": urls,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    if save_to_db:
        sink = load_sink()
        if sink is None:
            raise typer.BadParameter(
                "Postgres não configurado. Defina as variáveis DB_* para usar --save-to-db."
            )
        sink.save_discovery_run(source_name, urls)
        typer.echo(f"URLs persistidas em discovery_runs para source_name={source_name}")

    typer.echo(f"{len(urls)} URLs descobertas. Salvas em: {output.discovered}")
