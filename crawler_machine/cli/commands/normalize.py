from __future__ import annotations

import json
import logging
from pathlib import Path

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import load_config, make_output, setup_logging
from crawler_machine.extermination.exterminator import Exterminator
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.pipeline.persistence import (
    save_normalized_output,
    save_quality_report,
    save_rejected_output,
)


@app.command()
def normalize(
    raw_file: Path = typer.Argument(
        ..., help="Arquivo JSON com dados brutos"
    ),
    config_path: Path = typer.Option(
        Path("config/domain.json"), "--config", help="Caminho do arquivo de configuração"
    ),
    output_dir: Path = typer.Option(
        Path("output"), "--output", help="Diretório base de saída"
    ),
) -> None:
    """Normaliza dados brutos extraídos."""
    setup_logging()
    config = load_config(config_path)

    with raw_file.open("r", encoding="utf-8") as f:
        raw_payload = json.load(f)

    raw_data = raw_payload.get("data", [])

    output = make_output(output_dir, raw_file.stem)
    output.prepare()

    exterminator = Exterminator()
    survivors, rejected = exterminator.filter(raw_data)

    normalizer = DataNormalizer()
    normalized, quality_report = normalizer.normalize_many(survivors, config.fields)

    save_normalized_output(output, normalized)
    save_rejected_output(output, rejected)
    save_quality_report(output, rejected, quality_report)

    logging.info(
        "%s registros normalizados | %s eliminados",
        len(normalized),
        len(rejected),
    )
    typer.echo(f"{len(normalized)} registros normalizados | {len(rejected)} eliminados")
    typer.echo(f"Resultado salvo em: {output.normalized}")
    if rejected:
        typer.echo(f"Registros eliminados em: {output.rejected}")
