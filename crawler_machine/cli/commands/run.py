from __future__ import annotations

import logging
from pathlib import Path

import typer
from tqdm import tqdm

from crawler_machine.cli.app import app
from crawler_machine.cli.builder import build_pipeline
from crawler_machine.cli.helpers import (
    check_api_key,
    load_config,
    load_env_file,
    load_sink,
    make_output,
    setup_logging,
)


@app.command()
def run(
    base_url: str = typer.Argument(..., help="URL base do site da imobiliária"),
    sample_url: str | None = typer.Option(
        None,
        "--sample-url",
        help="URL de exemplo para geração do schema (opcional se schema já cacheado no Postgres)",
    ),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Caminho do arquivo de configuração"
    ),
    output_dir: Path = typer.Option(
        Path("output"), "--output", help="Diretório base de saída"
    ),
    source_name: str = typer.Option(
        ..., "--source-name", help="Nome da fonte/imobiliária (slug usado no banco)"
    ),
    regenerate_discovery: bool = typer.Option(
        False,
        "--regenerate-discovery",
        help="Força nova descoberta de URLs, ignorando cache",
    ),
    regenerate_schema: bool = typer.Option(
        False,
        "--regenerate-schema",
        help="Força nova geração de schema via LLM, ignorando cache",
    ),
    enable_llm_fallback: bool = typer.Option(
        False,
        "--enable-llm-fallback",
        help="Habilita fallback por LLM sobre HTML completo",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Logs detalhados"),
) -> None:
    """Executa o pipeline completo."""
    setup_logging(verbose)
    load_env_file()
    config = load_config(config_path)
    check_api_key(config)

    output = make_output(output_dir, base_url)
    logging.info(f"Saída: {output.root}")

    sink = load_sink()
    if sink is not None:
        logging.info("Postgres sink ativado")

    with tqdm(total=100, desc="pipeline", unit="%") as progress_bar:
        pipeline = build_pipeline(
            config,
            output,
            progress_bar,
            verbose=verbose,
            sink=sink,
            source_name=source_name,
            enable_llm_fallback=enable_llm_fallback,
        )
        result = pipeline.run_sync(
            base_url,
            sample_url=sample_url,
            regenerate_discovery=regenerate_discovery,
            regenerate_schema=regenerate_schema,
        )

    logging.info(
        f"Pipeline concluído: {len(result.normalized)} registros normalizados"
    )
    logging.info(f"Erros: {len(result.errors)}")
    if result.run_id is not None:
        logging.info(f"Run salvo no Postgres: {result.run_id}")
    logging.info(f"Artefatos salvos em: {output.root}")
