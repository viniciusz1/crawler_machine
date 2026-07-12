from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class PostgresConfig:
    host: str
    port: int
    database: str
    user: str
    password: str

    @classmethod
    def from_env(cls) -> "PostgresConfig | None":
        host = os.environ.get("DB_HOST")
        port = os.environ.get("DB_PORT")
        database = os.environ.get("DB_DATABASE")
        user = os.environ.get("DB_USERNAME")
        password = os.environ.get("DB_PASSWORD")

        if not all([host, port, database, user, password]):
            return None

        return cls(
            host=host,
            port=int(port),
            database=database,
            user=user,
            password=password,
        )
