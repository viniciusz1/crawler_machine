from __future__ import annotations

from typing import Any

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
