from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
import yaml

from crawler_machine.cli.helpers import (
    generate_prospecting_run_id,
    get_custom_search_credentials,
    get_places_api_key,
    load_env_file,
    load_prospect_repository,
    setup_logging,
)
from crawler_machine.prospecting.models import Candidate
from crawler_machine.prospecting.output import write_candidates
from crawler_machine.prospecting.parsing import CityParseError, parse_cities
from crawler_machine.prospecting.places import GooglePlacesGateway
from crawler_machine.prospecting.prospector import Prospector
from crawler_machine.prospecting.sample_finder import (
    EnrichedCandidate,
    GoogleCustomSearchGateway,
    SampleEnricher,
)

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


@prospecting_app.command("enrich-samples")
def enrich_samples(
    input_file: Path = typer.Argument(
        ..., help="Arquivo YAML de candidatos gerado pelo prospecting find."
    ),
    out: Path | None = typer.Option(
        None,
        "--out",
        help="Arquivo de saída (default: <input>.enriched.yaml).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Imprime as queries sem chamar a API.",
    ),
    skip_existing: bool = typer.Option(
        False,
        "--skip-existing",
        help="Preserva sample_url já existentes no arquivo de saída.",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Logs detalhados"),
) -> None:
    """Enriquece candidatos com sample_url via Google Custom Search API."""
    setup_logging(verbose)
    load_env_file()

    if not input_file.exists():
        raise typer.BadParameter(f"Arquivo não encontrado: {input_file}")

    if out is None:
        out = input_file.with_suffix(".enriched.yaml")

    raw = yaml.safe_load(input_file.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise typer.BadParameter("YAML de entrada deve ser um documento com 'candidates'.")

    candidates = _load_candidates(raw.get("candidates", []))
    if not candidates:
        typer.echo("Nenhum candidato encontrado no arquivo de entrada.")
        return

    _ensure_unique_source_names(candidates)

    if dry_run:
        _dry_run(candidates)
        return

    api_key, cx = get_custom_search_credentials()
    gateway = GoogleCustomSearchGateway(api_key=api_key, cx=cx)
    enricher = SampleEnricher(gateway)

    existing: list[EnrichedCandidate] = []
    to_enrich = candidates
    if skip_existing and out.exists():
        existing, to_enrich = _split_existing(candidates, out)

    enriched = enricher.enrich(to_enrich)
    enriched = existing + enriched

    _write_enriched(enriched, out)

    found = sum(1 for e in enriched if e.sample_url is not None)
    missing = len(enriched) - found
    typer.echo(f"Enriquecimento concluído: {found} com sample_url, {missing} sem.")
    typer.echo(f"Salvo em: {out}")


def _load_candidates(raw_candidates: list[Any]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for item in raw_candidates:
        if not isinstance(item, dict):
            continue
        if item.get("status") != "candidate":
            continue
        candidates.append(
            Candidate(
                city=item.get("city", ""),
                state=item.get("state", ""),
                name=item.get("name", ""),
                base_url=item.get("base_url"),
                source_name=item.get("source_name"),
                phone=item.get("phone"),
                address=item.get("address"),
                google_place_id=item.get("google_place_id"),
                source=item.get("source", "google_places"),
                status=item.get("status", "candidate"),
                reject_reason=item.get("reject_reason"),
            )
        )
    return candidates


def _ensure_unique_source_names(candidates: list[Candidate]) -> None:
    seen: set[str] = set()
    for candidate in candidates:
        source_name = candidate.source_name or ""
        if source_name in seen:
            raise typer.BadParameter(f"source_name duplicado: {source_name}")
        seen.add(source_name)


def _dry_run(candidates: list[Candidate]) -> None:
    typer.echo("Modo dry-run. Queries que seriam executadas:")
    for candidate in candidates:
        source_name = candidate.source_name or "desconhecido"
        typer.echo(f"\n{source_name}:")
        for property_type in SampleEnricher._PROPERTY_TYPES:
            for query in SampleEnricher.build_queries(
                candidate.base_url or "", property_type, candidate.city, candidate.state
            ):
                typer.echo(f"  - {query}")


def _split_existing(
    candidates: list[Candidate], existing_path: Path
) -> tuple[list[EnrichedCandidate], list[Candidate]]:
    existing_raw = yaml.safe_load(existing_path.read_text(encoding="utf-8"))
    if not isinstance(existing_raw, list):
        return [], candidates

    existing_by_source: dict[str, EnrichedCandidate] = {}
    for item in existing_raw:
        if isinstance(item, dict) and item.get("source_name"):
            existing_by_source[item["source_name"]] = EnrichedCandidate(
                base_url=item.get("base_url", ""),
                source_name=item["source_name"],
                sample_url=item.get("sample_url"),
            )

    existing: list[EnrichedCandidate] = []
    to_enrich: list[Candidate] = []
    for candidate in candidates:
        source_name = candidate.source_name or ""
        if (
            source_name in existing_by_source
            and existing_by_source[source_name].sample_url is not None
        ):
            existing.append(existing_by_source[source_name])
        else:
            to_enrich.append(candidate)
    return existing, to_enrich


def _write_enriched(enriched: list[EnrichedCandidate], path: Path) -> None:
    output = [
        {
            "base_url": item.base_url,
            "source_name": item.source_name,
            "sample_url": item.sample_url,
        }
        for item in enriched
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(output, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
