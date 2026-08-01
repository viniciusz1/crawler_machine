import os

import psycopg2
import pytest
from dotenv import load_dotenv

from tests.crawler_schema import ensure_schema
from tests.database_safety import database_tests_enabled

load_dotenv()


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
    )


@pytest.mark.skipif(
    not database_tests_enabled(),
    reason="Dedicated Postgres test database not configured",
)
def test_ensure_schema_creates_crawler_catalog_tables():
    """O helper de teste consegue criar as tabelas esperadas localmente.

    O schema real é mantido fora deste repositório; este teste cobre apenas o
    helper usado pelos testes Python quando o ambiente externo não está ativo.
    """
    connection = _connect()
    try:
        ensure_schema(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'crawler'
                ORDER BY table_name
                """
            )
            tables = {row[0] for row in cursor.fetchall()}

        assert "cities" in tables
        assert "neighborhoods" in tables
        assert "property_types" in tables
        assert "crawler_runs" in tables
        assert "discovery_runs" in tables
        assert "schema_runs" in tables
        assert "raw_properties" in tables
        assert "market_properties" in tables
    finally:
        connection.close()
