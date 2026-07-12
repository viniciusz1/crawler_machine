from crawler_machine.catalog import Catalog, CatalogRepository
from crawler_machine.normalization.engine import DataNormalizer


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
            },
            property_types={
                "apartamento": {"id": 1, "name": "Apartamento", "slug": "apartamento", "aliases": ["apto"]},
            },
        )
    )


def test_normalizer_applies_semantic_normalization():
    normalizer = DataNormalizer(catalog_repository=_repo(), city_slug="jaragua-do-sul")
    record = {
        "tipo_imovel": "apto",
        "bairro": "Centro",
        "cidade": "jaragua do sul",
    }

    result = normalizer.normalize(record)

    assert result["tipo_imovel"] == "Apartamento"
    assert result["bairro"] == "Centro"
    assert result["cidade"] == "Jaraguá do Sul"


def test_normalizer_adds_quality_metadata_for_unknown_values():
    normalizer = DataNormalizer(catalog_repository=_repo(), city_slug="jaragua-do-sul")
    record = {
        "tipo_imovel": "Castelo",
        "bairro": "Moema",
        "cidade": "Joinville",
    }

    result = normalizer.normalize(record)

    assert result["tipo_imovel"] == "Castelo"
    assert result["bairro"] == "Moema"
    assert result["cidade"] == "Joinville"
    assert result["_quality"]["valid"] is False
    assert len(result["_quality"]["warnings"]) == 3


def test_normalizer_generates_quality_report():
    normalizer = DataNormalizer(catalog_repository=_repo(), city_slug="jaragua-do-sul")
    records = [
        {"tipo_imovel": "apto", "bairro": "Centro", "cidade": "jaragua do sul"},
        {"tipo_imovel": "Castelo", "bairro": "Moema", "cidade": "Joinville"},
    ]

    normalized, report = normalizer.normalize_many(records)

    assert len(normalized) == 2
    assert report["total_records"] == 2
    assert report["records_with_issues"] == [1]


def test_normalizer_computes_strategy_usage_metrics():
    normalizer = DataNormalizer()
    records = [
        {
            "valor": "R$ 100.000,00",
            "_extraction_trace": {"valor": "xpath", "url": "url"},
        },
        {
            "valor": "R$ 200.000,00",
            "_extraction_trace": {"valor": "css", "url": "url"},
        },
        {
            "bairro": "Centro",
            "_extraction_trace": {"bairro": "fit_markdown_llm", "url": "url"},
        },
    ]

    normalized, report = normalizer.normalize_many(records)

    assert report["strategy_usage"]["xpath"]["fields"]["valor"] == 1
    assert report["strategy_usage"]["css"]["fields"]["valor"] == 1
    assert report["strategy_usage"]["fit_markdown_llm"]["fields"]["bairro"] == 1
    assert report["llm_calls"]["fit_markdown_llm"] == 1
    assert report["llm_calls"]["llm_full_html"] == 0
