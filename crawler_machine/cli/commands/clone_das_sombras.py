from __future__ import annotations

import logging
from pathlib import Path

import typer

from crawler_machine.batch import BatchError, run_batch
from crawler_machine.cli.app import app
from crawler_machine.cli.builder import build_batch_runner
from crawler_machine.cli.helpers import (
    check_api_key,
    load_config,
    load_env_file,
    load_sink,
    setup_logging,
)


@app.command()
def clone_das_sombras(
    yaml_file: Path = typer.Argument(
        ..., help="Arquivo YAML com a lista de imobiliárias"
    ),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Caminho do arquivo de configuração"
    ),
    output_dir: Path = typer.Option(
        Path("output"), "--output", help="Diretório base de saída"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Logs detalhados"),
) -> None:
    """Processa um batch de imobiliárias a partir de um arquivo YAML."""
    setup_logging(verbose)
    load_env_file()
    config = load_config(config_path)
    check_api_key(config)

    sink = load_sink()
    if sink is not None:
        logging.info("Postgres sink ativado")

    runner = build_batch_runner(
        config=config,
        output_dir=output_dir,
        verbose=verbose,
        sink=sink,
    )

    try:
        report = run_batch(yaml_file, output_dir=output_dir, runner=runner)
    except BatchError as exc:
        raise typer.BadParameter(str(exc)) from exc

    logging.info(
        f"Batch concluído: {report['metadata']['succeeded']} sucesso(s), "
        f"{report['metadata']['failed']} falha(s) de {report['metadata']['total']} total"
    )
    logging.info(f"Relatório salvo em: {output_dir}/batch_report_*.json")
