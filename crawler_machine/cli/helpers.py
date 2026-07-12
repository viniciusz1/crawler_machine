from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import typer
from dotenv import load_dotenv

from crawler_machine.config import ConfigLoader, DomainConfig
from crawler_machine.output import OutputPath
from crawler_machine.prospecting.repository import ProspectRepository
from crawler_machine.sink import PostgresConfig, RunStore
from crawler_machine.sink.prospect_repository import PostgresProspectRepository


def load_config(config_path: Path) -> DomainConfig:
    if not config_path.exists():
        raise typer.BadParameter(
            f"Arquivo de configuração não encontrado: {config_path}"
        )
    return ConfigLoader.load(config_path)


def load_env_file() -> None:
    env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path)


def check_api_key(config: DomainConfig) -> None:
    api_key = os.environ.get(config.llm.api_key_env)
    if not api_key:
        raise typer.BadParameter(
            f"Variável de ambiente {config.llm.api_key_env} não definida. "
            "Crie um arquivo .env na raiz do projeto."
        )


def get_places_api_key() -> str:
    """Lê a ``GOOGLE_PLACES_API_KEY`` do ambiente ou levanta erro amigável."""
    api_key = os.environ.get("GOOGLE_PLACES_API_KEY")
    if not api_key:
        raise typer.BadParameter(
            "Variável de ambiente GOOGLE_PLACES_API_KEY não definida. "
            "Crie um arquivo .env na raiz do projeto com sua chave da "
            "Google Places API."
        )
    return api_key


def slugify_domain(domain: str) -> str:
    return domain.replace("https://", "").replace("http://", "").replace(".", "-")


def make_output(base_dir: Path, domain: str) -> OutputPath:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return OutputPath(base_dir=base_dir, domain=domain, timestamp=timestamp)


def load_sink() -> RunStore | None:
    config = PostgresConfig.from_env()
    if config is None:
        return None
    return RunStore(config)


def load_prospect_repository() -> ProspectRepository | None:
    config = PostgresConfig.from_env()
    if config is None:
        return None
    return PostgresProspectRepository(config)


def generate_prospecting_run_id() -> str:
    suffix = os.urandom(2).hex()
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"prospecting_{timestamp}_{suffix}"


def detect_schema_type_from_data(schema_data: dict[str, Any]) -> str:
    """Detecta se o schema é XPATH ou CSS baseado nos seletores."""
    selectors = [schema_data.get("baseSelector", "")]
    for field in schema_data.get("fields", []):
        if "selector" in field:
            selectors.append(field["selector"])

    if any(
        isinstance(s, str) and (s.startswith("//") or s.startswith(".//"))
        for s in selectors
    ):
        return "XPATH"
    return "CSS"


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
