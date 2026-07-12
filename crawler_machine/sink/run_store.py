from __future__ import annotations

import json
import logging
from typing import Any

from psycopg2.extras import execute_values

from crawler_machine.sink.builders import build_market_rows, build_raw_rows
from crawler_machine.sink.columns import MARKET_PROPERTY_COLUMNS, RAW_PROPERTY_COLUMNS
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.connection import connect

logger = logging.getLogger(__name__)


class RunStore:
    """Destino Postgres para execuções do crawler.

    Centraliza todo o ciclo de vida das execuções (crawler, discovery e schema)
    em um único módulo profundo, responsável por conexão, transação e linking.
    """

    def __init__(self, config: PostgresConfig):
        self._config = config

    def catalog_repository(self) -> "CatalogRepository":
        """Retorna um repositório de catálogo conectado ao Postgres."""
        from crawler_machine.catalog import CatalogRepository

        import psycopg2

        connection = psycopg2.connect(
            host=self._config.host,
            port=self._config.port,
            dbname=self._config.database,
            user=self._config.user,
            password=self._config.password,
        )
        try:
            return CatalogRepository.from_postgres(connection)
        finally:
            connection.close()

    def start_run(self, source_name: str) -> int:
        """Cria um crawler run inicial com status ``running``."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.crawler_runs
                            (source_name, status, started_at, latest)
                        VALUES (%s, %s, NOW(), FALSE)
                        RETURNING id
                        """,
                        (source_name, "running"),
                    )
                    return cursor.fetchone()[0]

    def fail_run(self, run_id: int, error_message: str) -> None:
        """Marca um crawler run como falho."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.crawler_runs
                        SET status = %s, completed_at = NOW(), error_message = %s
                        WHERE id = %s
                        """,
                        ("failed", error_message, run_id),
                    )

    def save_run(
        self,
        source_name: str,
        raw_properties: list[dict[str, Any]],
        normalized_properties: list[dict[str, Any]],
        errors: list[dict[str, Any]],
    ) -> int:
        """Salva uma execução completa e retorna o ID do run criado."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.crawler_runs
                            (source_name, status, started_at, completed_at, properties_count, latest)
                        VALUES (%s, %s, NOW(), NOW(), %s, TRUE)
                        RETURNING id
                        """,
                        (source_name, "completed", len(normalized_properties)),
                    )
                    run_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        UPDATE crawler.crawler_runs
                        SET latest = FALSE
                        WHERE source_name = %s AND id != %s
                        """,
                        (source_name, run_id),
                    )

                    raw_ids: list[int] = []
                    if raw_properties:
                        raw_rows = build_raw_rows(
                            run_id, raw_properties, RAW_PROPERTY_COLUMNS
                        )
                        execute_values(
                            cursor,
                            f"""
                            INSERT INTO crawler.raw_properties (
                                {", ".join(RAW_PROPERTY_COLUMNS)}
                            ) VALUES %s
                            RETURNING id
                            """,
                            raw_rows,
                        )
                        raw_ids = [row[0] for row in cursor.fetchall()]

                    if normalized_properties:
                        market_rows = build_market_rows(
                            run_id,
                            normalized_properties,
                            raw_ids,
                            source_name,
                            MARKET_PROPERTY_COLUMNS,
                        )
                        execute_values(
                            cursor,
                            f"""
                            INSERT INTO crawler.market_properties (
                                {", ".join(MARKET_PROPERTY_COLUMNS)}
                            ) VALUES %s
                            """,
                            market_rows,
                        )

                    logger.info(
                        "Run %s salvo para %s com %s propriedades",
                        run_id,
                        source_name,
                        len(normalized_properties),
                    )
                    return run_id

    def start_discovery_run(self, source_name: str) -> int:
        """Cria um discovery run inicial com status ``running``."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.discovery_runs
                            (source_name, status, started_at, latest)
                        VALUES (%s, %s, NOW(), FALSE)
                        RETURNING id
                        """,
                        (source_name, "running"),
                    )
                    return cursor.fetchone()[0]

    def save_discovery_run(self, source_name: str, urls: list[str]) -> int:
        """Salva um discovery run completo e retorna o ID."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.discovery_runs
                            (source_name, status, urls, started_at, completed_at, latest)
                        VALUES (%s, %s, %s, NOW(), NOW(), TRUE)
                        RETURNING id
                        """,
                        (source_name, "completed", json.dumps(urls)),
                    )
                    run_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        UPDATE crawler.discovery_runs
                        SET latest = FALSE
                        WHERE source_name = %s AND id != %s
                        """,
                        (source_name, run_id),
                    )

                    logger.info(
                        "Discovery run %s salvo para %s com %s URLs",
                        run_id,
                        source_name,
                        len(urls),
                    )
                    return run_id

    def fail_discovery_run(self, run_id: int, error_message: str) -> None:
        """Marca um discovery run como falho."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.discovery_runs
                        SET status = %s, completed_at = NOW(), error_message = %s
                        WHERE id = %s
                        """,
                        ("failed", error_message, run_id),
                    )

    def load_latest_discovery(self, source_name: str) -> list[str] | None:
        """Retorna as URLs do discovery run mais recente com status ``completed``."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT urls FROM crawler.discovery_runs
                        WHERE source_name = %s AND status = %s AND latest = TRUE
                        LIMIT 1
                        """,
                        (source_name, "completed"),
                    )
                    row = cursor.fetchone()
                    if row is None or row[0] is None:
                        return None
                    return row[0]

    def link_discovery_run(
        self, discovery_run_id: int, crawler_run_id: int
    ) -> None:
        """Vincula um discovery run a um crawler run."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE crawler.discovery_runs SET crawler_run_id = %s WHERE id = %s",
                        (crawler_run_id, discovery_run_id),
                    )

    def start_schema_run(self, source_name: str) -> int:
        """Cria um schema run inicial com status ``running``."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.schema_runs
                            (source_name, status, started_at, latest)
                        VALUES (%s, %s, NOW(), FALSE)
                        RETURNING id
                        """,
                        (source_name, "running"),
                    )
                    return cursor.fetchone()[0]

    def save_schema_run(
        self,
        source_name: str,
        schema_data: dict[str, Any],
        schema_type: str,
        sample_url: str,
        fields_snapshot: list[dict[str, Any]],
    ) -> int:
        """Salva um schema run completo e retorna o ID."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO crawler.schema_runs
                            (source_name, status, schema_data, schema_type, sample_url,
                             fields_snapshot, started_at, completed_at, latest)
                        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), TRUE)
                        RETURNING id
                        """,
                        (
                            source_name,
                            "completed",
                            json.dumps(schema_data),
                            schema_type,
                            sample_url,
                            json.dumps(fields_snapshot),
                        ),
                    )
                    run_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        UPDATE crawler.schema_runs
                        SET latest = FALSE
                        WHERE source_name = %s AND id != %s
                        """,
                        (source_name, run_id),
                    )

                    logger.info(
                        "Schema run %s salvo para %s (type=%s)",
                        run_id,
                        source_name,
                        schema_type,
                    )
                    return run_id

    def fail_schema_run(self, run_id: int, error_message: str) -> None:
        """Marca um schema run como falho."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE crawler.schema_runs
                        SET status = %s, completed_at = NOW(), error_message = %s
                        WHERE id = %s
                        """,
                        ("failed", error_message, run_id),
                    )

    def load_latest_schema(self, source_name: str) -> dict[str, Any] | None:
        """Retorna o schema_data do schema run mais recente com status ``completed``."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT schema_data FROM crawler.schema_runs
                        WHERE source_name = %s AND status = %s AND latest = TRUE
                        LIMIT 1
                        """,
                        (source_name, "completed"),
                    )
                    row = cursor.fetchone()
                    if row is None or row[0] is None:
                        return None
                    return row[0]

    def link_schema_run(self, schema_run_id: int, crawler_run_id: int) -> None:
        """Vincula um schema run a um crawler run."""
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE crawler.schema_runs SET crawler_run_id = %s WHERE id = %s",
                        (crawler_run_id, schema_run_id),
                    )
