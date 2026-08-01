from __future__ import annotations

from typing import Any

from crawler_machine.worker.validation import ProfileValidationExecutor


class FakeExtractor:
    def __init__(self, missing_title_urls: set[str] | None = None) -> None:
        self._missing_title_urls = missing_title_urls or set()

    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> tuple[dict[str, Any] | None, list[str]]:
        assert "xpath" in schemas
        record: dict[str, Any] = {"url": url, "price": "100000"}
        if url not in self._missing_title_urls:
            record["title"] = f"Property {url.rsplit('/', 1)[-1]}"
        return record, []


class FakeNormalizer:
    def normalize(
        self,
        record: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        invalid = int(str(record["url"]).rsplit("/", 1)[-1]) > 16
        normalized = {
            **record,
            "_quality": {
                "valid": not invalid,
                "warnings": ["normalization warning"] if invalid else [],
            },
        }
        if invalid:
            normalized.pop("title", None)
        return normalized


class OptionalWarningNormalizer:
    def normalize(
        self,
        record: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            **record,
            "_quality": {
                "valid": False,
                "warnings": ["optional boolean was omitted"],
            },
        }


def _plan(url_count: int = 20) -> dict[str, Any]:
    return {
        "urls": [f"https://example.com/property/{index}" for index in range(1, url_count + 1)],
        "schemas": {"xpath": {"baseSelector": "//body", "fields": []}},
        "fields": [
            {"name": "title", "type": "string", "required": True},
            {"name": "price", "type": "decimal", "required": False},
        ],
        "thresholds": {"valid_ratio": 0.80, "required_field_coverage": 0.90},
    }


def test_validation_is_eligible_at_exact_limits_and_keeps_per_url_evidence() -> None:
    report = ProfileValidationExecutor(
        extractor=FakeExtractor(), normalizer=FakeNormalizer()
    ).run(_plan())

    assert report["sampled_url_count"] == 20
    assert report["valid_record_count"] == 16
    assert report["valid_ratio"] == 0.80
    assert report["required_field_coverage"] == {"title": 1.0}
    assert report["blocking_failures"] == []
    assert report["warnings"] == ["normalization warning"]
    assert report["eligible"] is True
    assert report["records"][0]["raw_data"]["title"] == "Property 1"
    assert report["records"][16]["is_valid"] is False


def test_required_coverage_below_ninety_percent_prevents_approval() -> None:
    missing = {
        "https://example.com/property/17",
        "https://example.com/property/18",
        "https://example.com/property/19",
    }
    report = ProfileValidationExecutor(
        extractor=FakeExtractor(missing), normalizer=FakeNormalizer()
    ).run(_plan())

    assert report["required_field_coverage"]["title"] == 0.85
    assert report["eligible"] is False


def test_no_valid_records_is_a_blocking_failure() -> None:
    report = ProfileValidationExecutor(
        extractor=FakeExtractor(), normalizer=FakeNormalizer()
    ).run(_plan(url_count=0))

    assert report["blocking_failures"] == ["no_urls_sampled", "no_valid_records"]
    assert report["eligible"] is False


def test_optional_normalization_warnings_do_not_invalidate_required_fields() -> None:
    report = ProfileValidationExecutor(
        extractor=FakeExtractor(), normalizer=OptionalWarningNormalizer()
    ).run(_plan(url_count=1))

    assert report["valid_record_count"] == 1
    assert report["valid_ratio"] == 1.0
    assert report["warnings"] == ["optional boolean was omitted"]
    assert report["records"][0]["is_valid"] is True
    assert report["eligible"] is True
