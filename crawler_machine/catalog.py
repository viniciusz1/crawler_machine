from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from unidecode import unidecode


def normalize_key(text: str) -> str:
    """Normaliza um texto para comparação no catálogo.

    Remove acentos, converte para minúsculas, remove espaços extras
    e substitui sequências de espaços por um único hífen.
    """
    text = unidecode(str(text).lower())
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


@dataclass(frozen=True)
class Catalog:
    """Catálogos carregados em memória para normalização semântica."""

    cities: dict[str, dict[str, Any]]
    neighborhoods: dict[str, dict[str, Any]]
    property_types: dict[str, dict[str, Any]]


class CatalogRepository:
    """Repositório de catálogos usado pelos normalizadores semânticos.

    O repositório trabalha com um ``Catalog`` já carregado em memória,
    permitindo que os dados venham do Postgres ou de um objeto fake em testes.
    """

    def __init__(self, catalog: Catalog):
        self._catalog = catalog
        self._cities_index = self._build_cities_index(catalog.cities)
        self._neighborhoods_index = self._build_neighborhoods_index(catalog.neighborhoods)
        self._property_types_index = self._build_property_types_index(catalog.property_types)

    @staticmethod
    def _build_cities_index(cities: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for city in cities.values():
            index[normalize_key(city["name"])] = city
            for alias in city.get("aliases", []) or []:
                index[normalize_key(alias)] = city
        return index

    @staticmethod
    def _build_neighborhoods_index(
        neighborhoods: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for neighborhood in neighborhoods.values():
            city_slug = neighborhood.get("city_slug")
            if not city_slug:
                continue
            base_key = f"{city_slug}:{normalize_key(neighborhood['name'])}"
            index[base_key] = neighborhood
            for alias in neighborhood.get("aliases", []) or []:
                index[f"{city_slug}:{normalize_key(alias)}"] = neighborhood
        return index

    @staticmethod
    def _build_property_types_index(
        property_types: dict[str, dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        index: dict[str, dict[str, Any]] = {}
        for property_type in property_types.values():
            index[normalize_key(property_type["name"])] = property_type
            for alias in property_type.get("aliases", []) or []:
                index[normalize_key(alias)] = property_type
        return index

    @classmethod
    def from_postgres(cls, connection: Any) -> "CatalogRepository":
        """Carrega os catálogos a partir de uma conexão Postgres."""
        cities: dict[str, dict[str, Any]] = {}
        neighborhoods: dict[str, dict[str, Any]] = {}
        property_types: dict[str, dict[str, Any]] = {}

        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name, slug, state FROM crawler.cities")
            for row in cursor.fetchall():
                city = {"id": row[0], "name": row[1], "slug": row[2], "state": row[3]}
                cities[row[2]] = city

            cursor.execute(
                "SELECT n.id, n.city_id, n.name, n.slug, n.aliases, c.slug AS city_slug "
                "FROM crawler.neighborhoods n JOIN crawler.cities c ON c.id = n.city_id"
            )
            for row in cursor.fetchall():
                neighborhood = {
                    "id": row[0],
                    "city_id": row[1],
                    "name": row[2],
                    "slug": row[3],
                    "aliases": row[4] or [],
                    "city_slug": row[5],
                }
                neighborhoods[f"{row[5]}:{row[3]}"] = neighborhood
                # índice por nome normalizado também
                neighborhoods[f"{row[5]}:{normalize_key(row[2])}"] = neighborhood
                for alias in neighborhood["aliases"]:
                    neighborhoods[f"{row[5]}:{normalize_key(alias)}"] = neighborhood

            cursor.execute("SELECT id, name, slug, aliases FROM crawler.property_types")
            for row in cursor.fetchall():
                property_type = {"id": row[0], "name": row[1], "slug": row[2], "aliases": row[3] or []}
                property_types[row[2]] = property_type
                property_types[normalize_key(row[1])] = property_type
                for alias in property_type["aliases"]:
                    property_types[normalize_key(alias)] = property_type

        return cls(Catalog(cities=cities, neighborhoods=neighborhoods, property_types=property_types))

    def find_city(self, raw_name: str) -> dict[str, Any] | None:
        """Busca uma cidade pelo nome normalizado."""
        return self._cities_index.get(normalize_key(raw_name))

    def find_neighborhood(self, city_slug: str, raw_name: str) -> dict[str, Any] | None:
        """Busca um bairro dentro de uma cidade pelo nome normalizado ou alias."""
        key = f"{city_slug}:{normalize_key(raw_name)}"
        return self._neighborhoods_index.get(key)

    def find_property_type(self, raw_name: str) -> dict[str, Any] | None:
        """Busca um tipo de imóvel pelo nome normalizado ou alias."""
        return self._property_types_index.get(normalize_key(raw_name))
