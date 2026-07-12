from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.run_store import RunStore


def _config() -> PostgresConfig:
    return PostgresConfig(
        host="localhost",
        port=5432,
        database="test",
        user="user",
        password="pass",
    )


def _mock_connection() -> MagicMock:
    mock_cursor = MagicMock()
    mock_cursor.fetchone.return_value = [42]
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_connection.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return mock_connection


def test_run_store_starts_run_as_running():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = store.start_run("imob-test")

    assert run_id == 42
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.crawler_runs" in call[0][0]
    assert call[0][1] == ("imob-test", "running")


def test_run_store_fails_run():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = None

    with patch("psycopg2.connect", return_value=mock_connection):
        store.fail_run(7, "timeout")

    mock_cursor.execute.assert_called_once_with(
        """
                        UPDATE crawler.crawler_runs
                        SET status = %s, completed_at = NOW(), error_message = %s
                        WHERE id = %s
                        """,
        ("failed", "timeout", 7),
    )


def test_run_store_saves_completed_run_and_flips_latest():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    raw_properties: list[dict[str, Any]] = [
        {
            "tipo_imovel": "Casa",
            "valor": "R$ 500.000,00",
            "quartos": "3",
            "piscina": "sim",
        }
    ]
    normalized_properties: list[dict[str, Any]] = [
        {
            "tipo_imovel": "Casa",
            "valor": 500000.0,
            "quartos": 3,
            "piscina": True,
            "_quality": {"valid": True, "warnings": []},
        }
    ]

    with patch("psycopg2.connect", return_value=mock_connection):
        with patch("crawler_machine.sink.run_store.execute_values") as mock_execute_values:
            run_id = store.save_run(
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


def test_run_store_saves_discovery_run():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = store.save_discovery_run(
            "imob-test",
            ["https://example.com/imovel/1", "https://example.com/imovel/2"],
        )

    assert run_id == 42
    insert_call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.discovery_runs" in insert_call[0][0]
    assert insert_call[0][1][0] == "imob-test"
    assert insert_call[0][1][1] == "completed"
    assert insert_call[0][1][2] == '["https://example.com/imovel/1", "https://example.com/imovel/2"]'

    update_call = mock_cursor.execute.call_args_list[1]
    assert "UPDATE crawler.discovery_runs" in update_call[0][0]
    assert "SET latest = FALSE" in update_call[0][0]
    assert update_call[0][1] == ("imob-test", 42)


def test_run_store_loads_latest_discovery():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = [["https://example.com/a", "https://example.com/b"]]

    with patch("psycopg2.connect", return_value=mock_connection):
        urls = store.load_latest_discovery("imob-test")

    assert urls == ["https://example.com/a", "https://example.com/b"]


def test_run_store_loads_latest_schema():
    config = _config()
    store = RunStore(config)
    expected_schema = {
        "name": "ImovelSchema",
        "baseSelector": "//body",
        "fields": [{"name": "quartos", "selector": "//span[@class='rooms']"}],
    }
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = [expected_schema]

    with patch("psycopg2.connect", return_value=mock_connection):
        schema = store.load_latest_schema("imob-test")

    assert schema == expected_schema


def test_run_store_saves_schema_run():
    config = _config()
    store = RunStore(config)
    schema_data = {"name": "TestSchema", "baseSelector": "div.property", "fields": []}
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    with patch("psycopg2.connect", return_value=mock_connection):
        run_id = store.save_schema_run(
            "imob-test",
            schema_data,
            "CSS",
            "https://example.com/imovel/1",
            [{"name": "quartos", "description": "Número de quartos"}],
        )

    assert run_id == 42
    insert_call = mock_cursor.execute.call_args_list[0]
    assert "INSERT INTO crawler.schema_runs" in insert_call[0][0]
    assert insert_call[0][1][0] == "imob-test"
    assert insert_call[0][1][1] == "completed"


def test_run_store_links_discovery_and_schema_runs():
    config = _config()
    store = RunStore(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    mock_cursor.fetchone.return_value = None

    with patch("psycopg2.connect", return_value=mock_connection):
        store.link_discovery_run(5, 10)
        store.link_schema_run(6, 10)

    assert mock_cursor.execute.call_count == 2
    calls = mock_cursor.execute.call_args_list
    assert calls[0][0] == (
        "UPDATE crawler.discovery_runs SET crawler_run_id = %s WHERE id = %s",
        (10, 5),
    )
    assert calls[1][0] == (
        "UPDATE crawler.schema_runs SET crawler_run_id = %s WHERE id = %s",
        (10, 6),
    )
