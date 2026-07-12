from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from crawler_machine.prospecting.models import Candidate, Place
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.prospect_repository import PostgresProspectRepository


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
    mock_cursor.fetchall.return_value = []
    mock_connection = MagicMock()
    mock_connection.cursor.return_value.__enter__ = MagicMock(
        return_value=mock_cursor
    )
    mock_connection.cursor.return_value.__exit__ = MagicMock(
        return_value=False
    )
    return mock_connection


def _place(name: str, website: str | None, place_id: str = "p1") -> Place:
    return Place(
        place_id=place_id,
        name=name,
        website=website,
        phone=None,
        address=None,
        city="Joinville",
        state="SC",
    )


def _candidate(
    name: str, base_url: str | None, status: str = "candidate"
) -> Candidate:
    return Candidate(
        city="Joinville",
        state="SC",
        name=name,
        base_url=base_url,
        source_name="imob-boa-com-br" if base_url else None,
        status=status,
        reject_reason=None if status == "candidate" else "aggregator",
        google_place_id="p1",
    )


def test_filter_new_places_queries_existing_domains():
    config = _config()
    repo = PostgresProspectRepository(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value
    mock_cursor.fetchall.return_value = [("imob-boa.com.br",)]

    places = [
        _place("Imob Boa", "https://imob-boa.com.br"),
        _place("Imob Nova", "https://imob-nova.com.br"),
    ]

    with patch("psycopg2.connect", return_value=mock_connection):
        result = repo.filter_new_places(places)

    assert len(result) == 1
    assert result[0].name == "Imob Nova"
    mock_cursor.execute.assert_called_once()
    call = mock_cursor.execute.call_args
    assert "SELECT root_domain FROM crawler.prospects" in call[0][0]


def test_filter_new_places_force_returns_all():
    config = _config()
    repo = PostgresProspectRepository(config)
    mock_connection = _mock_connection()

    places = [
        _place("Imob Boa", "https://imob-boa.com.br"),
        _place("Imob Nova", "https://imob-nova.com.br"),
    ]

    with patch("psycopg2.connect", return_value=mock_connection):
        result = repo.filter_new_places(places, force=True)

    assert len(result) == 2
    mock_connection.cursor.assert_not_called()


def test_save_candidates_upserts_rows():
    config = _config()
    repo = PostgresProspectRepository(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    candidates = [
        _candidate("Imob Boa", "https://imob-boa.com.br", "candidate"),
        _candidate("ZAP", "https://zapimoveis.com.br", "rejected"),
    ]

    with patch("psycopg2.connect", return_value=mock_connection):
        repo.save_candidates(candidates, "run-1")

    mock_cursor.executemany.assert_called_once()
    call = mock_cursor.executemany.call_args
    assert "INSERT INTO crawler.prospects" in call[0][0]
    assert "ON CONFLICT (root_domain) DO UPDATE" in call[0][0]
    assert len(call[0][1]) == 2


def test_save_candidates_empty_list_does_nothing():
    config = _config()
    repo = PostgresProspectRepository(config)
    mock_connection = _mock_connection()
    mock_cursor = mock_connection.cursor.return_value.__enter__.return_value

    with patch("psycopg2.connect", return_value=mock_connection):
        repo.save_candidates([], "run-1")

    mock_cursor.executemany.assert_not_called()
