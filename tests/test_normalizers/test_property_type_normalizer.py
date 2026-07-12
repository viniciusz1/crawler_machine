from crawler_machine.catalog import Catalog, CatalogRepository
from crawler_machine.normalization.normalizers.property_type_normalizer import PropertyTypeNormalizer


def _repo() -> CatalogRepository:
    return CatalogRepository(
        Catalog(
            cities={},
            neighborhoods={},
            property_types={
                "apartamento": {"id": 1, "name": "Apartamento", "slug": "apartamento", "aliases": ["apto"]},
                "sobrado-geminado": {
                    "id": 2,
                    "name": "Sobrado Geminado",
                    "slug": "sobrado-geminado",
                    "aliases": [],
                },
            },
        )
    )


def test_normalizes_known_property_type():
    normalizer = PropertyTypeNormalizer(_repo())
    result = normalizer.normalize("Apartamento")
    assert result.value == "Apartamento"
    assert result.is_valid is True
    assert result.warnings == []


def test_normalizes_property_type_by_alias():
    normalizer = PropertyTypeNormalizer(_repo())
    result = normalizer.normalize("Apto")
    assert result.value == "Apartamento"
    assert result.is_valid is True


def test_keeps_unknown_property_type_with_warning():
    normalizer = PropertyTypeNormalizer(_repo())
    result = normalizer.normalize("Castelo")
    assert result.value == "Castelo"
    assert result.is_valid is False
    assert any("fora do catálogo" in w for w in result.warnings)


def test_returns_none_for_empty_value():
    normalizer = PropertyTypeNormalizer(_repo())
    result = normalizer.normalize("  ")
    assert result.value is None
    assert result.omitted is True
