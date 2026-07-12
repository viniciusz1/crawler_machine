import os

import psycopg2
import pytest
from dotenv import load_dotenv

from crawler_machine.catalog import Catalog, CatalogRepository
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


def _sample_catalog() -> Catalog:
    return Catalog(
        cities={
            "jaragua-do-sul": {"id": 1, "name": "Jaraguá do Sul", "slug": "jaragua-do-sul", "state": "SC"},
        },
        neighborhoods={
            "jaragua-do-sul:centro": {
                "id": 1,
                "name": "Centro",
                "slug": "centro",
                "city_id": 1,
                "city_slug": "jaragua-do-sul",
            },
            "jaragua-do-sul:vila-lenzi": {
                "id": 2,
                "name": "Vila Lenzi",
                "slug": "vila-lenzi",
                "city_id": 1,
                "city_slug": "jaragua-do-sul",
                "aliases": ["vila lenzi"],
            },
        },
        property_types={
            "apartamento": {"id": 1, "name": "Apartamento", "slug": "apartamento", "aliases": ["apto"]},
            "sobrado-geminado": {"id": 2, "name": "Sobrado Geminado", "slug": "sobrado-geminado", "aliases": []},
        },
    )


def test_find_property_type_by_name():
    repo = CatalogRepository(_sample_catalog())
    result = repo.find_property_type("Apartamento")
    assert result is not None
    assert result["slug"] == "apartamento"


def test_find_property_type_by_alias():
    repo = CatalogRepository(_sample_catalog())
    result = repo.find_property_type("Apto")
    assert result is not None
    assert result["slug"] == "apartamento"


def test_find_property_type_not_found():
    repo = CatalogRepository(_sample_catalog())
    assert repo.find_property_type("Castelo") is None


def test_find_city_by_name_with_accents_and_case():
    repo = CatalogRepository(_sample_catalog())
    result = repo.find_city("jaragua do sul")
    assert result is not None
    assert result["slug"] == "jaragua-do-sul"


def test_find_neighborhood_by_name():
    repo = CatalogRepository(_sample_catalog())
    result = repo.find_neighborhood("jaragua-do-sul", "Centro")
    assert result is not None
    assert result["slug"] == "centro"


def test_find_neighborhood_by_alias():
    repo = CatalogRepository(_sample_catalog())
    result = repo.find_neighborhood("jaragua-do-sul", "VILA LENZI")
    assert result is not None
    assert result["slug"] == "vila-lenzi"


def test_find_neighborhood_not_found():
    repo = CatalogRepository(_sample_catalog())
    assert repo.find_neighborhood("jaragua-do-sul", "Moema") is None


@pytest.mark.skipif(not os.getenv("DB_HOST"), reason="Postgres not configured")
def test_from_postgres_loads_catalogs():
    connection = _connect()
    try:
        ensure_schema(connection)
        seed_test_catalogs(connection)
        repo = CatalogRepository.from_postgres(connection)

        city = repo.find_city("Jaraguá do Sul")
        assert city is not None
        assert city["slug"] == "jaragua-do-sul"

        neighborhood = repo.find_neighborhood("jaragua-do-sul", "Centro")
        assert neighborhood is not None
        assert neighborhood["slug"] == "centro"

        property_type = repo.find_property_type("Sobrado Geminado")
        assert property_type is not None
        assert property_type["slug"] == "sobrado-geminado"
    finally:
        connection.close()
