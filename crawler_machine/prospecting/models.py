from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class CityTarget:
    """Cidade-alvo de prospecção, informada manualmente pelo operador.

    A UF é obrigatória para desambiguar homônimos (ex.: dezenas de
    "São João" no Brasil).
    """

    name: str
    state: str

    @property
    def label(self) -> str:
        return f"{self.name}, {self.state}"


@dataclass(frozen=True)
class Place:
    """Resultado bruto de uma busca no Google Places para uma cidade.

    ``website`` pode ser ``None`` quando o place não tem site cadastrado —
    nesse caso o lugar é descartado durante a classificação.
    """

    place_id: str
    name: str
    website: str | None
    phone: str | None
    address: str | None
    city: str
    state: str
    source: str = "google_places"


@dataclass(frozen=True)
class Candidate:
    """Candidato a imobiliária, após classificação e filtro.

    ``status`` é ``candidate`` (aprovado para revisão humana) ou
    ``rejected`` (agregador, sem website ou domínio duplicado).
    """

    city: str
    state: str
    name: str
    base_url: str | None
    source_name: str | None
    sample_url: str | None = None
    phone: str | None = None
    address: str | None = None
    google_place_id: str | None = None
    source: str = "google_places"
    status: str = "candidate"
    reject_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Summary:
    total: int
    candidates: int
    rejected: int


@dataclass(frozen=True)
class ProspectingResult:
    """Resultado consolidado de uma execução de prospecção."""

    query_cities: list[str]
    candidates: list[Candidate]
    summary: Summary
    save_errors: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> list[Candidate]:
        return [c for c in self.candidates if c.status == "candidate"]

    @property
    def rejected(self) -> list[Candidate]:
        return [c for c in self.candidates if c.status == "rejected"]
