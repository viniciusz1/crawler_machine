from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, call, patch

import pytest

from crawler_machine.sink import (
    PostgresConfig,
    PostgresSink,
    build_source_name,
)
from crawler_machine.sink.coercion import (
    coerce_for_column,
    rename_fields,
    to_boolean,
    to_float,
    to_int,
)


def test_build_source_name_from_url():
    assert build_source_name("https://imbsmart.com.br") == "imbsmart-com-br"


def test_build_source_name_from_explicit_name():
    assert build_source_name("https://example.com", "Imobiliária Modelo") == "imobiliaria-modelo"


def testrename_fields_maps_crawler_names_to_db_columns():
    record = {
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "detalhes": "Descrição",
        "area_util": 72.5,
        "ano": 2020,
    }
    renamed = rename_fields(record)
    assert renamed == {
        "tipo": "Apartamento",
        "link_imovel": "https://example.com/imovel/1",
        "descricao": "Descrição",
        "area": 72.5,
        "ano_construcao": 2020,
    }


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        (1, True),
        (0, False),
        ("sim", True),
        ("não", False),
        (None, None),
    ],
)
def testto_boolean(value, expected):
    assert to_boolean(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("R$ 450.000,00", 450000.0),
        ("1.234,56", 1234.56),
        ("72,5 m²", 72.5),
        (None, None),
        ("", None),
    ],
)
def testto_float(value, expected):
    assert to_float(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("3 (sendo 1 suíte)", 3),
        ("2020", 2020),
        (None, None),
    ],
)
def testto_int(value, expected):
    assert to_int(value) == expected


def testcoerce_for_column_preserves_strings():
    assert coerce_for_column("  Centro  ", "bairro") == "Centro"
    assert coerce_for_column("", "bairro") is None


def test_postgres_config_from_env_requires_all_fields():
    with patch.dict("os.environ", {"DB_HOST": "localhost"}, clear=True):
        assert PostgresConfig.from_env() is None

    env = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_DATABASE": "imob",
        "DB_USERNAME": "user",
        "DB_PASSWORD": "pass",
    }
    with patch.dict("os.environ", env, clear=True):
        config = PostgresConfig.from_env()
        assert config == PostgresConfig(
            host="localhost",
            port=5432,
            database="imob",
            user="user",
            password="pass",
        )


def test_save_run_persists_run_and_properties_atomically():
    config = PostgresConfig(
        host="localhost",
        port=5432,
        database="test",
        user="user",
        password="pass",
    )
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [42]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        with patch("crawler_machine.sink.run_store.execute_values") as mock_execute_values:
            raw_properties = [
                {
                    "tipo_imovel": "Casa",
                    "valor": "R$ 500.000,00",
                    "quartos": "3",
                    "piscina": "sim",
                }
            ]
            normalized_properties = [
                {
                    "tipo_imovel": "Casa",
                    "valor": 500000.0,
                    "quartos": 3,
                    "piscina": True,
                    "_quality": {"valid": True, "warnings": []},
                }
            ]
            run_id = sink.save_run(
                "imob-test",
                raw_properties,
                normalized_properties,
                [],
            )

    assert run_id == 42
    mock_cursor.execute.assert_any_call(
        """
                        INSERT INTO crawler.crawler_runs
                            (source_name, status, started_at, completed_at, properties_count, latest)
                        VALUES (%s, %s, NOW(), NOW(), %s, TRUE)
                        RETURNING id
                        """,
        ("imob-test", "completed", 1),
    )
    mock_cursor.execute.assert_any_call(
        """
                        UPDATE crawler.crawler_runs
                        SET latest = FALSE
                        WHERE source_name = %s AND id != %s
                        """,
        ("imob-test", 42),
    )
    assert mock_execute_values.call_count == 2
    calls = mock_execute_values.call_args_list
    assert "crawler.raw_properties" in calls[0][0][1]
    assert "crawler.market_properties" in calls[1][0][1]
    assert calls[0][0][0] is mock_cursor
    assert calls[1][0][0] is mock_cursor


def test_fail_run_updates_status_and_error():
    config = PostgresConfig(
        host="localhost",
        port=5432,
        database="test",
        user="user",
        password="pass",
    )
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        sink.fail_run(7, "timeout")

    mock_cursor.execute.assert_called_once_with(
        """
                        UPDATE crawler.crawler_runs
                        SET status = %s, completed_at = NOW(), error_message = %s
                        WHERE id = %s
                        """,
        ("failed", "timeout", 7),
    )


def test_save_discovery_run_persists_and_flips_latest():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [10]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = sink.save_discovery_run("imob-test", ["https://example.com/imovel/1", "https://example.com/imovel/2"])

    assert run_id == 10

    insert_call = mock_cursor.execute.call_args_list[0]
    assert insert_call[0][0].strip().startswith("INSERT INTO crawler.discovery_runs")
    assert insert_call[0][1][0] == "imob-test"
    assert insert_call[0][1][1] == "completed"
    assert insert_call[0][1][2] == '["https://example.com/imovel/1", "https://example.com/imovel/2"]'

    update_call = mock_cursor.execute.call_args_list[1]
    assert "UPDATE crawler.discovery_runs" in update_call[0][0]
    assert "SET latest = FALSE" in update_call[0][0]
    assert update_call[0][1] == ("imob-test", 10)


def test_load_latest_discovery_returns_urls():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [["https://example.com/a", "https://example.com/b"]]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        urls = sink.load_latest_discovery("imob-test")

    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_load_latest_discovery_returns_none_when_no_rows():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        urls = sink.load_latest_discovery("imob-test")

    assert urls is None


def test_start_discovery_run_creates_running_row():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [5]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = sink.start_discovery_run("imob-test")

    assert run_id == 5
    call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.discovery_runs" in call[0][0]
    assert call[0][1] == ("imob-test", "running")


def test_fail_discovery_run_updates_status():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        sink.fail_discovery_run(3, "no urls found")

    mock_cursor.execute.assert_called_once()
    call = mock_cursor.execute.call_args_list[0]
    assert "UPDATE crawler.discovery_runs" in call[0][0]
    assert call[0][1] == ("failed", "no urls found", 3)


# --- crawler.schema_runs tests ---


def test_save_schema_run_persists_and_flips_latest():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [7]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    schema_data = {"name": "TestSchema", "baseSelector": "div.property", "fields": []}
    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = sink.save_schema_run(
            "imob-test",
            schema_data,
            "CSS",
            "https://example.com/imovel/1",
            [{"name": "quartos", "description": "Número de quartos"}],
        )

    assert run_id == 7
    insert_call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.schema_runs" in insert_call[0][0]
    assert insert_call[0][1][0] == "imob-test"
    assert insert_call[0][1][1] == "completed"

    update_call = mock_cursor.execute.call_args_list[1]
    assert "UPDATE crawler.schema_runs" in update_call[0][0]
    assert "SET latest = FALSE" in update_call[0][0]


def test_load_latest_schema_returns_schema_data():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    expected_schema = {"name": "ImovelSchema", "baseSelector": "//body", "fields": [{"name": "quartos", "selector": "//span[@class='rooms']"}]}
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [expected_schema]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        schema = sink.load_latest_schema("imob-test")

    assert schema == expected_schema


def test_load_latest_schema_returns_none_when_no_rows():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = None
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        schema = sink.load_latest_schema("imob-test")

    assert schema is None


def test_start_schema_run_creates_running_row():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [3]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = sink.start_schema_run("imob-test")

    assert run_id == 3
    call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.schema_runs" in call[0][0]
    assert call[0][1] == ("imob-test", "running")


def test_fail_schema_run_updates_status():
    config = PostgresConfig(host="localhost", port=5432, database="test", user="user", password="pass")
    sink = PostgresSink(config)

    mock_cursor = MagicMock()
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)

    with patch("psycopg2.connect", return_value=mock_connection):
        sink.fail_schema_run(5, "LLM timeout")

    mock_cursor.execute.assert_called_once()
    call = mock_cursor.execute.call_args_list[0]
    assert "UPDATE crawler.schema_runs" in call[0][0]
    assert call[0][1] == ("failed", "LLM timeout", 5)
