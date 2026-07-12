from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import typer

from crawler_machine.cli.app import app
from crawler_machine.cli.helpers import (
    check_api_key,
    detect_schema_type_from_data,
    load_config,
    load_env_file,
    load_sink,
    make_output,
    setup_logging,
)
from crawler_machine.schema_generator import SchemaGenerator


@app.command()
def schema(
    sample_url: str = typer.Argument(
        ..., help="URL de exemplo para gerar o schema"
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
    save_to_db: bool = typer.Option(
        False, "--save-to-db", help="Persiste o schema gerado no Postgres"
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Logs detalhados"),
) -> None:
    """Gera um schema de extração a partir de uma URL de exemplo."""
    setup_logging(verbose)
    load_env_file()
    config = load_config(config_path)
    check_api_key(config)

    output = make_output(output_dir, sample_url)
    generator = SchemaGenerator(
        llm_config=config.llm, fields=config.fields, verbose=verbose
    )
    schema_data = generator.generate_sync(sample_url)

    output.schema.parent.mkdir(parents=True, exist_ok=True)
    with output.schema.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "metadata": {
                    "sample_url": sample_url,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                "schema": schema_data,
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
        schema_type = detect_schema_type_from_data(schema_data)
        fields_snapshot = [
            {"name": f.name, "description": f.description, "coerce": f.coerce}
            for f in config.fields
        ]
        sink.save_schema_run(
            source_name, schema_data, schema_type, sample_url, fields_snapshot
        )
        typer.echo(f"Schema persistido em schema_runs para source_name={source_name}")

    typer.echo(f"Schema gerado e salvo em: {output.schema}")
