from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

import psycopg2
from psycopg2.extensions import connection as PgConnection

from crawler_machine.sink.config import PostgresConfig


@contextmanager
def connect(config: PostgresConfig) -> Generator[PgConnection, None, None]:
    """Abre uma conexão com o Postgres e a fecha ao sair do contexto."""
    connection = psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.database,
        user=config.user,
        password=config.password,
    )
    try:
        yield connection
    finally:
        connection.close()
