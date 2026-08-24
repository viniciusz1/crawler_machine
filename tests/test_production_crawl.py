from __future__ import annotations

from typing import Any

from crawler_machine.catalog import Catalog, CatalogRepository
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.worker.production import ProductionCrawlExecutor


class FakeDiscoverer:
    def discover_sync(self, base_url: str) -> list[str]:
        assert base_url == "https://agency.example.com"
        return [
            "https://agency.example.com/property/1",
            "https://agency.example.com/property/2",
        ]


class FakeExtractor:
    def __init__(self, fail_on: str | None = None) -> None:
        self._fail_on = fail_on

    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, list[str]]:
        if url == self._fail_on:
            raise RuntimeError("browser crashed")
        if url.endswith("/2"):
            return {"url": url, "title": "Missing price"}, []
        return {
            "url": url,
            "title": "House",
            "valor": "200000",
            "_extraction_trace": {"title": "xpath", "valor": "css"},
        }, []


class BatchExtractor:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def extract_many(
        self,
        urls: list[str],
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> list[tuple[dict[str, Any] | None, list[str]]]:
        self.calls.append(list(urls))
        return [
            (
                {
                    "url": url,
                    "title": "House",
                    "valor": "200000",
                    "_extraction_trace": {"title": "xpath"},
                },
                [],
            )
            for url in urls
        ]

    def extract(self, *args, **kwargs):
        raise AssertionError("the production crawl should use extract_many")


class FakeNormalizer:
    def normalize(
        self,
        record: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **record,
            "valor": 200000,
            "_quality": {"valid": True, "warnings": ["review value"]},
        }


class SmartCurrencyExtractor:
    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        return {"url": url, "title": "Apartamento", "valor": "R$ 329.000"}, []


class PropertyTypeExtractor:
    def __init__(self, property_type: str) -> None:
        self._property_type = property_type

    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> tuple[dict[str, Any], list[str]]:
        return {"url": url, "tipo_imovel": self._property_type}, []


def _property_type_normalizer() -> DataNormalizer:
    catalog = Catalog(
        cities={},
        neighborhoods={},
        property_types={
            "apartamento": {
                "id": 1,
                "name": "Apartamento",
                "slug": "apartamento",
                "aliases": ["apto", "apartamento em condomínio"],
            }
        },
    )
    return DataNormalizer(
        property_type_catalog_repository=CatalogRepository(catalog)
    )


def _plan(discovery: dict[str, Any]) -> dict[str, Any]:
    return {
        "crawl_agency_id": 42,
        "discovery": discovery,
        "extraction_profile": {
            "id": 7,
            "schemas": {"xpath": {}},
        },
        "market_data_contract": {
            "id": 3,
            "fields": [
                {"name": "title", "required": True},
                {"name": "valor", "required": True},
            ],
        },
        "quality_policy": {"id": 1, "rules": {}},
    }


def _property_type_plan(url: str) -> dict[str, Any]:
    plan = _plan({"mode": "existing", "snapshot_id": 5, "urls": [url]})
    plan["market_data_contract"]["fields"] = [
        {"name": "url", "required": True, "coerce": "string"},
        {"name": "tipo_imovel", "required": True, "coerce": "string"},
    ]
    return plan


def test_production_crawl_normalizes_property_type_alias():
    url = "https://agency.example.com/property/1"

    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=PropertyTypeExtractor("apartamento em condomínio"),
        normalizer=_property_type_normalizer(),
    ).run(_property_type_plan(url))

    assert result["market_properties"][0]["payload"]["tipo_imovel"] == "Apartamento"
    assert result["rejected_properties"] == []


def test_production_crawl_rejects_unknown_required_property_type():
    url = "https://agency.example.com/property/1"

    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=PropertyTypeExtractor("Millenium"),
        normalizer=_property_type_normalizer(),
    ).run(_property_type_plan(url))

    assert result["market_properties"] == []
    assert result["rejected_properties"][0]["missing_fields"] == ["tipo_imovel"]
    assert result["publishable"] is False


def test_existing_snapshot_crawl_keeps_raw_normalized_rejected_and_trace() -> None:
    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(),
        normalizer=FakeNormalizer(),
    ).run(
        _plan(
            {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": [
                    "https://agency.example.com/property/1",
                    "https://agency.example.com/property/2",
                ],
            }
        )
    )

    assert result["technical_state"] == "succeeded"
    assert result["result_kind"] == "full"
    assert result["publishable"] is True
    assert len(result["raw_properties"]) == 2
    assert result["market_properties"][0]["normalization_warnings"] == ["review value"]
    assert result["market_properties"][0]["extraction_trace"]["valor"] == "css"
    assert result["rejected_properties"][0]["missing_fields"] == ["valor"]


def test_production_crawl_reports_processed_url_progress() -> None:
    progress: list[tuple[int, int]] = []
    executor = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(),
        normalizer=FakeNormalizer(),
    )

    executor.run(
        _plan(
            {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": [
                    "https://agency.example.com/property/1",
                    "https://agency.example.com/property/2",
                ],
            }
        ),
        on_progress=lambda processed, total: progress.append((processed, total)),
    )

    assert progress == [(1, 2), (2, 2)]


def test_production_crawl_extracts_all_urls_in_one_batch() -> None:
    extractor = BatchExtractor()
    urls = [
        "https://agency.example.com/property/1",
        "https://agency.example.com/property/2",
    ]

    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=extractor,
        normalizer=FakeNormalizer(),
    ).run(_plan({"mode": "existing", "snapshot_id": 5, "urls": urls}))

    assert result["technical_state"] == "succeeded"
    assert extractor.calls == [urls]
    assert len(result["raw_properties"]) == 2


def test_production_crawl_uses_the_approved_detail_url_shape() -> None:
    plan = _plan(
        {
            "mode": "existing",
            "snapshot_id": 5,
            "urls": [
                "https://agency.example.com/imoveis/venda/casa",
                "https://agency.example.com/imovel/property/1",
                "https://agency.example.com/imovel/property/2",
            ],
        }
    )
    plan["extraction_profile"]["parameters"] = {
        "sample_url": "https://agency.example.com/imovel/property/1"
    }

    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(),
        normalizer=FakeNormalizer(),
    ).run(plan)

    assert [row["url"] for row in result["raw_properties"]] == [
        "https://agency.example.com/imovel/property/1",
        "https://agency.example.com/imovel/property/2",
    ]


def test_production_crawl_preserves_smart_currency_thousands() -> None:
    url = "https://imbsmart.com.br/imovel/329000"
    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=SmartCurrencyExtractor(),
    ).run(
        _plan({"mode": "existing", "snapshot_id": 5, "urls": [url]})
    )

    assert result["raw_properties"][0]["payload"]["valor"] == "R$ 329.000"
    assert result["market_properties"][0]["payload"]["valor"] == 329_000.0


def test_fresh_crawl_discovers_urls_inside_the_operation() -> None:
    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(),
        normalizer=FakeNormalizer(),
    ).run(_plan({"mode": "fresh", "base_url": "https://agency.example.com"}))

    assert result["discovery"]["mode"] == "fresh"
    assert len(result["discovery"]["urls"]) == 2


def test_fatal_failure_preserves_partial_rows_and_never_marks_them_publishable() -> None:
    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(fail_on="https://agency.example.com/property/2"),
        normalizer=FakeNormalizer(),
    ).run(
        _plan(
            {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": [
                    "https://agency.example.com/property/1",
                    "https://agency.example.com/property/2",
                ],
            }
        )
    )

    assert result["technical_state"] == "failed"
    assert result["result_kind"] == "partial"
    assert result["publishable"] is False
    assert len(result["raw_properties"]) == 1
    assert result["errors"][0]["message"] == "browser crashed"


def test_cooperative_cancellation_stops_between_urls_and_preserves_partial_data() -> None:
    checks = iter([False, True])
    result = ProductionCrawlExecutor(
        discoverer=FakeDiscoverer(),
        extractor=FakeExtractor(),
        normalizer=FakeNormalizer(),
    ).run(
        _plan(
            {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": [
                    "https://agency.example.com/property/1",
                    "https://agency.example.com/property/2",
                ],
            }
        ),
        should_cancel=lambda: next(checks),
    )

    assert result["technical_state"] == "cancelled"
    assert result["result_kind"] == "partial"
    assert result["publishable"] is False
    assert len(result["raw_properties"]) == 1
