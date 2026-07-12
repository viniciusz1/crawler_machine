from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from crawler_machine.prospecting.filters import root_domain
from crawler_machine.prospecting.models import Candidate, Place


class ProspectRepository(ABC):
    """Contrato para persistência e consulta de prospects.

    A implementação concreta pode ser em memória (testes) ou Postgres
    (produção). A interface é mínima e focada nas operações necessárias
    para deduplicar domínios durante a prospecção.
    """

    @abstractmethod
    def filter_new_places(
        self, places: list[Place], force: bool = False
    ) -> list[Place]:
        """Retorna lugares cujo domínio raiz ainda não foi prospectado.

        Quando ``force`` é ``True``, retorna todos os lugares, permitindo
        reprocessar domínios já prospectados.
        """

    @abstractmethod
    def save_candidates(
        self, candidates: list[Candidate], run_id: str
    ) -> None:
        """Persiste uma lista de candidatos classificados.

        Cada candidato é identificado pelo domínio raiz do ``base_url``.
        Domínios já existentes são sobrescritos (upsert).
        """


@dataclass
class InMemoryProspectRepository(ProspectRepository):
    """Implementação em memória de ``ProspectRepository`` para testes."""

    _storage: dict[str, dict[str, Any]] = field(default_factory=dict)

    def filter_new_places(
        self, places: list[Place], force: bool = False
    ) -> list[Place]:
        if force:
            return list(places)
        return [
            place
            for place in places
            if root_domain(place.website or "") not in self._storage
        ]

    def save_candidates(
        self, candidates: list[Candidate], run_id: str
    ) -> None:
        for candidate in candidates:
            domain = root_domain(candidate.base_url or "")
            if not domain:
                continue
            self._storage[domain] = {
                "run_id": run_id,
                "candidate": candidate,
            }

    def count(self) -> int:
        return len(self._storage)

    def get(self, domain: str) -> dict[str, Any] | None:
        return self._storage.get(domain)
