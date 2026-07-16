from __future__ import annotations

import json
import logging
from typing import Any

from crawler_machine.prospecting.filters import root_domain
from crawler_machine.prospecting.models import Candidate, Place
from crawler_machine.prospecting.repository import ProspectRepository
from crawler_machine.sink.config import PostgresConfig
from crawler_machine.sink.connection import connect

logger = logging.getLogger(__name__)


class PostgresProspectRepository(ProspectRepository):
    """Implementação Postgres de ``ProspectRepository``.

    Assume que a tabela ``crawler.prospects`` já existe (criada e versionada
    fora deste repositório). Usa ``root_domain(base_url)`` como chave natural
    para deduplicação e upsert.
    """

    _COLUMNS = (
        "root_domain",
        "google_place_id",
        "name",
        "city",
        "state",
        "base_url",
        "phone",
        "address",
        "source",
        "automatic_classification",
        "automatic_reason",
        "metadata",
    )

    def __init__(self, config: PostgresConfig) -> None:
        self._config = config

    def filter_new_places(
        self, places: list[Place], force: bool = False
    ) -> list[Place]:
        if force:
            return list(places)

        domains = [
            root_domain(place.website or "")
            for place in places
            if place.website
        ]
        if not domains:
            return list(places)

        existing = self._existing_domains(domains)
        return [
            place
            for place in places
            if root_domain(place.website or "") not in existing
        ]

    def save_candidates(
        self, candidates: list[Candidate], run_id: str
    ) -> None:
        if not candidates:
            return

        rows = [self._to_row(candidate, run_id) for candidate in candidates]
        self._upsert_rows(rows)

    def _existing_domains(self, domains: list[str]) -> set[str]:
        if not domains:
            return set()

        placeholders = ",".join(["%s"] * len(domains))
        query = f"""
            SELECT root_domain FROM crawler.prospects
            WHERE root_domain IN ({placeholders})
        """
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, domains)
                    return {row[0] for row in cursor.fetchall()}

    def _to_row(self, candidate: Candidate, run_id: str) -> tuple[Any, ...]:
        payload: dict[str, Any] = {
            "google_place_id": candidate.google_place_id,
            "phone": candidate.phone,
            "address": candidate.address,
            "prospecting_run_id": run_id,
        }
        return (
            root_domain(candidate.base_url or "") or None,
            candidate.google_place_id or "",
            candidate.name,
            candidate.city,
            candidate.state,
            candidate.base_url,
            candidate.phone,
            candidate.address,
            candidate.source,
            candidate.status,
            candidate.reject_reason,
            json.dumps(payload, ensure_ascii=False),
        )

    def _upsert_rows(self, rows: list[tuple[Any, ...]]) -> None:
        columns = ", ".join(self._COLUMNS)
        placeholders = ", ".join(["%s"] * len(self._COLUMNS))
        update_columns = ", ".join(
            f"{col} = EXCLUDED.{col}"
            for col in self._COLUMNS
            if col != "root_domain"
        )
        query = f"""
            INSERT INTO crawler.prospects ({columns}, created_at, updated_at)
            VALUES ({placeholders}, NOW(), NOW())
            ON CONFLICT (root_domain) DO UPDATE SET
                {update_columns}, updated_at = NOW()
        """
        with connect(self._config) as connection:
            with connection:
                with connection.cursor() as cursor:
                    cursor.executemany(query, rows)
                    logger.debug("Persistidos %s prospects", len(rows))
