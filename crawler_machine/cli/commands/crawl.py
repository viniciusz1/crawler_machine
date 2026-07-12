from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import load_config, make_output, setup_logging
from crawler_machine.extraction.factory import build_crawl_engine


@app.command()
def crawl(
    schema_file: Path = typer.Argument(
        ..., help="Arquivo JSON com o schema"
    ),
    urls_file: Path = typer.Argument(
        ..., help="Arquivo JSON com as URLs descobertas"
    ),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Caminho do arquivo de configuração"
    ),
    output_dir: Path = typer.Option(
        Path("output"), "--output", help="Diretório base de saída"
    ),
    enable_llm_fallback: bool = typer.Option(
        False,
        "--enable-llm-fallback",
        help="Habilita fallback por LLM sobre HTML completo",
    ),
) -> None:
    """Executa o crawler usando um schema e uma lista de URLs."""
    setup_logging()
    config = load_config(config_path)

    with schema_file.open("r", encoding="utf-8") as f:
        schema_payload = json.load(f)

    schema_data = schema_payload.get("schemas", schema_payload)
    if "xpath" not in schema_data and "css" not in schema_data:
        schema_data = {"schemas": {"xpath": schema_data, "css": schema_data}}

    with urls_file.open("r", encoding="utf-8") as f:
        urls_payload = json.load(f)

    urls = urls_payload.get("urls", urls_payload.get("data", []))

    output = make_output(output_dir, urls[0] if urls else "unknown")
    crawler = build_crawl_engine(
        config=config,
        schema=schema_data,
        enable_llm_fallback=enable_llm_fallback,
    )
    data, errors = crawler.crawl_sync(urls)

    output.raw.parent.mkdir(parents=True, exist_ok=True)
    with output.raw.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "crawled_at": datetime.now(timezone.utc).isoformat(),
                    "count": len(data),
                    "error_count": len(errors),
                },
                "data": data,
                "errors": errors,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    typer.echo(f"{len(data)} registros extraídos | {len(errors)} erros")
    typer.echo(f"Resultado salvo em: {output.raw}")
