from crawler_machine.catalog import Catalog, CatalogRepository
from crawler_machine.normalization.normalizers.neighborhood_normalizer import NeighborhoodNormalizer


def _repo() -> CatalogRepository:
    return CatalogRepository(
        Catalog(
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
            property_types={},
        )
    )


def test_normalizes_known_neighborhood():
    normalizer = NeighborhoodNormalizer(_repo(), city_slug="jaragua-do-sul")
    result = normalizer.normalize("Centro")
    assert result.value == "Centro"
    assert result.is_valid is True


def test_keeps_unknown_neighborhood_with_warning():
    normalizer = NeighborhoodNormalizer(_repo(), city_slug="jaragua-do-sul")
    result = normalizer.normalize("Moema")
    assert result.value == "Moema"
    assert result.is_valid is False
    assert any("fora do catálogo" in w for w in result.warnings)


def test_returns_none_for_empty_value():
    normalizer = NeighborhoodNormalizer(_repo(), city_slug="jaragua-do-sul")
    result = normalizer.normalize(None)
    assert result.value is None
    assert result.omitted is True
