from __future__ import annotations

import logging
from pathlib import Path

import typer
from dotenv import load_dotenv

from crawler_machine.config import ConfigLoader, DomainConfig


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


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
