from __future__ import annotations

from typing import Any

from crawler_machine.worker.production import ProductionCrawlExecutor
from crawler_machine.worker.validation import ProfileValidationExecutor


class PolicyCapturingExtractor:
    def __init__(self) -> None:
        self.policies: list[dict[str, Any] | None] = []

    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], list[str]]:
        self.policies.append(extraction_policy)
        return {
            "url": url,
            "title": "Property",
            "_extraction_trace": {"title": "css"},
        }, []


class ValidNormalizer:
    def normalize(
        self,
        record: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {**record, "_quality": {"valid": True, "warnings": []}}


class UnusedDiscoverer:
    def discover_sync(self, base_url: str) -> list[str]:
        raise AssertionError("existing discovery snapshot should be reused")


class PolicyCapturingDiscoverer:
    def __init__(self) -> None:
        self.policies: list[dict[str, Any] | None] = []

    def discover_sync(
        self,
        base_url: str,
        policy: dict[str, Any] | None = None,
    ) -> list[str]:
        self.policies.append(policy)
        return [f"{base_url}/property/1"]


def _fixed_policy() -> dict[str, Any]:
    return {
        "id": "019c-fixed-policy",
        "name": "CSS only",
        "version": 3,
        "source": "versioned_policy",
        "strategies": ["css"],
        "configuration": {},
    }


def test_validation_passes_the_unchanged_fixed_policy_to_every_extraction() -> None:
    extractor = PolicyCapturingExtractor()
    policy = _fixed_policy()
    report = ProfileValidationExecutor(
        extractor=extractor,
        normalizer=ValidNormalizer(),
    ).run(
        {
            "urls": [
                "https://example.com/property/1",
                "https://example.com/property/2",
            ],
            "schemas": {"css": {"baseSelector": "body", "fields": []}},
            "fields": [{"name": "title", "required": True}],
            "thresholds": {
                "valid_ratio": 0.8,
                "required_field_coverage": 0.9,
            },
            "extraction_policy": policy,
        }
    )

    assert report["eligible"] is True
    assert extractor.policies == [policy, policy]


def test_production_prefers_the_fixed_policy_persisted_with_the_profile() -> None:
    extractor = PolicyCapturingExtractor()
    policy = _fixed_policy()
    result = ProductionCrawlExecutor(
        discoverer=UnusedDiscoverer(),
        extractor=extractor,
        normalizer=ValidNormalizer(),
    ).run(
        {
            "crawl_agency_id": 42,
            "discovery": {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": ["https://example.com/property/1"],
            },
            "extraction_profile": {
                "id": 7,
                "schemas": {"css": {"baseSelector": "body", "fields": []}},
                "strategies": ["xpath"],
                "parameters": {"extraction_policy": policy},
            },
            "market_data_contract": {
                "id": 3,
                "fields": [{"name": "title", "required": True}],
            },
            "quality_policy": {"id": 1, "rules": {}},
        }
    )

    assert result["technical_state"] == "succeeded"
    assert extractor.policies == [policy]


def test_production_uses_profile_strategy_selection_for_legacy_profiles() -> None:
    extractor = PolicyCapturingExtractor()
    result = ProductionCrawlExecutor(
        discoverer=UnusedDiscoverer(),
        extractor=extractor,
        normalizer=ValidNormalizer(),
    ).run(
        {
            "crawl_agency_id": 42,
            "discovery": {
                "mode": "existing",
                "snapshot_id": 5,
                "urls": ["https://example.com/property/1"],
            },
            "extraction_profile": {
                "id": 7,
                "schemas": {"css": {"baseSelector": "body", "fields": []}},
                "strategies": ["css"],
                "parameters": {},
            },
            "market_data_contract": {
                "id": 3,
                "fields": [{"name": "title", "required": True}],
            },
            "quality_policy": {"id": 1, "rules": {}},
        }
    )

    assert result["technical_state"] == "succeeded"
    assert extractor.policies == [
        {"source": "extraction_profile", "strategies": ["css"]}
    ]


def test_fresh_first_production_uses_the_pinned_discovery_policy() -> None:
    extractor = PolicyCapturingExtractor()
    discoverer = PolicyCapturingDiscoverer()
    discovery_policy = {
        "id": 9,
        "version": 2,
        "source": "catalog",
        "strategies": ["sitemap", "homepage"],
        "configuration": {"max_urls": 100},
    }

    result = ProductionCrawlExecutor(
        discoverer=discoverer,
        extractor=extractor,
        normalizer=ValidNormalizer(),
    ).run(
        {
            "crawl_agency_id": 42,
            "discovery": {
                "mode": "fresh",
                "requested_mode": "fresh",
                "base_url": "https://example.com",
            },
            "discovery_policy": discovery_policy,
            "extraction_policy": _fixed_policy(),
            "extraction_profile": {
                "id": 7,
                "schemas": {"css": {"baseSelector": "body", "fields": []}},
                "strategies": ["css"],
                "parameters": {},
            },
            "market_data_contract": {
                "id": 3,
                "fields": [{"name": "title", "required": True}],
            },
            "quality_policy": {"id": 1, "rules": {}},
        }
    )

    assert result["technical_state"] == "succeeded"
    assert discoverer.policies == [discovery_policy]
