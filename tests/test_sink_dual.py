import os

import psycopg2
import pytest
from dotenv import load_dotenv

from crawler_machine.sink import PostgresConfig, PostgresSink
from tests.catalog_seed import seed_test_catalogs
from tests.crawler_schema import ensure_schema

load_dotenv()


def _connect():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
    )


@pytest.fixture
def sink():
    config = PostgresConfig(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT")),
        database=os.getenv("DB_DATABASE"),
        user=os.getenv("DB_USERNAME"),
        password=os.getenv("DB_PASSWORD"),
    )
    connection = _connect()
    ensure_schema(connection)
    seed_test_catalogs(connection)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                TRUNCATE TABLE
                    crawler.crawler_runs,
                    crawler.discovery_runs,
                    crawler.schema_runs,
                    crawler.raw_properties,
                    crawler.market_properties
                RESTART IDENTITY CASCADE
                """
            )
    connection.close()
    return PostgresSink(config)


@pytest.mark.skipif(not os.getenv("DB_HOST"), reason="Postgres not configured")
def test_save_run_persists_raw_and_normalized_properties(sink):
    raw_properties = [
        {
            "url": "https://example.com/1",
            "tipo_imovel": "Apartamento",
            "valor": "R$ 450.000,00",
            "bairro": "Centro",
            "cidade": "Jaraguá do Sul",
            "quartos": "3",
        }
    ]
    normalized_properties = [
        {
            "url": "https://example.com/1",
            "tipo_imovel": "Apartamento",
            "valor": 450000.0,
            "bairro": "Centro",
            "cidade": "Jaraguá do Sul",
            "quartos": 3,
            "_quality": {"valid": True, "warnings": []},
        }
    ]

    run_id = sink.save_run("test-source", raw_properties, normalized_properties, [])

    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, raw_payload FROM crawler.raw_properties WHERE crawler_run_id = %s",
                (run_id,),
            )
            raw_rows = cursor.fetchall()
            assert len(raw_rows) == 1
            raw_id = raw_rows[0][0]
            assert raw_rows[0][1]["valor"] == "R$ 450.000,00"

            cursor.execute(
                "SELECT raw_property_id, valor, quality_status, quality_metadata "
                "FROM crawler.market_properties WHERE crawler_run_id = %s",
                (run_id,),
            )
            market_rows = cursor.fetchall()
            assert len(market_rows) == 1
            assert market_rows[0][0] == raw_id
            assert market_rows[0][1] == 450000.0
            assert market_rows[0][2] == "valid"
            assert market_rows[0][3]["valid"] is True
    finally:
        connection.close()
