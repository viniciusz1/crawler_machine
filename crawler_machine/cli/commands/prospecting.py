from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import typer

from crawler_machine.cli.helpers import (
    generate_prospecting_run_id,
    get_places_api_key,
    load_env_file,
    load_prospect_repository,
    setup_logging,
)
from crawler_machine.prospecting.output import write_candidates
from crawler_machine.prospecting.parsing import CityParseError, parse_cities
from crawler_machine.prospecting.places import GooglePlacesGateway
from crawler_machine.prospecting.prospector import Prospector

prospecting_app = typer.Typer(help="Descoberta de imobiliárias candidatas por cidade.")


@prospecting_app.command("find")
def find(
    cities: str = typer.Option(
        ...,
        "--cities",
        help="Lista no formato 'Cidade,UF;Cidade,UF' (UF obrigatória).",
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Arquivo de saída (default: output/prospecting/candidatos_<ts>.yaml).",
    ),
    max_per_city: int = typer.Option(
        30, "--max-per-city", help="Máximo de resultados por cidade (Places API)."
    ),
    fmt: str = typer.Option(
        "yaml", "--format", help="Formato de saída: 'yaml' ou 'json'."
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Reprocessa domínios já prospectados e atualiza o banco.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Logs detalhados"),
) -> None:
    """Busca imobiliárias candidatas em cidades via Google Places API."""
    setup_logging(verbose)
    load_env_file()

    if fmt not in ("yaml", "json"):
        raise typer.BadParameter(f"formato inválido: {fmt} (use 'yaml' ou 'json')")

    api_key = get_places_api_key()
    repository = load_prospect_repository()
    run_id = generate_prospecting_run_id() if repository is not None else None

    if repository is None:
        logging.info(
            "Postgres não configurado; prospecção executará em modo degradado "
            "(YAML apenas)."
        )

    try:
        targets = parse_cities(cities)
    except CityParseError as exc:
        raise typer.BadParameter(str(exc)) from exc

    gateway = GooglePlacesGateway(api_key)
    result = Prospector(
        targets,
        gateway,
        repository=repository,
        run_id=run_id,
        max_per_city=max_per_city,
        force=force,
    ).run()

    if out is None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out = Path("output/prospecting") / timestamp / f"candidates.{fmt}"

    write_candidates(result, out, fmt=fmt)

    message = (
        f"{result.summary.candidates} candidato(s), "
        f"{result.summary.rejected} rejeitado(s) de {result.summary.total}. "
        f"Salvo em: {out}"
    )
    if result.save_errors:
        message += f". Atenção: {len(result.save_errors)} cidade(s) não salvas no banco."
    typer.echo(message)
