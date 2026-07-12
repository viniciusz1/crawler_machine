from crawler_machine.catalog import Catalog, CatalogRepository
from crawler_machine.normalization.normalizers.city_normalizer import CityNormalizer


def _repo() -> CatalogRepository:
    return CatalogRepository(
        Catalog(
            cities={
                "jaragua-do-sul": {"id": 1, "name": "Jaraguá do Sul", "slug": "jaragua-do-sul", "state": "SC"},
            },
            neighborhoods={},
            property_types={},
        )
    )


def test_normalizes_known_city():
    normalizer = CityNormalizer(_repo())
    result = normalizer.normalize("jaragua do sul")
    assert result.value == "Jaraguá do Sul"
    assert result.is_valid is True


def test_keeps_unknown_city_with_warning():
    normalizer = CityNormalizer(_repo())
    result = normalizer.normalize("Joinville")
    assert result.value == "Joinville"
    assert result.is_valid is False
    assert any("fora do catálogo" in w for w in result.warnings)


def test_returns_none_for_empty_value():
    normalizer = CityNormalizer(_repo())
    result = normalizer.normalize("")
    assert result.value is None
    assert result.omitted is True
