from __future__ import annotations

from typing import Any, Protocol

from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.worker.validation import ProfileExtractor, RecordNormalizer


class SynchronousDiscoverer(Protocol):
    def discover_sync(self, base_url: str) -> list[str]: ...


class ProductionCrawlExecutor:
    def __init__(
        self,
        discoverer: SynchronousDiscoverer,
        extractor: ProfileExtractor,
        normalizer: RecordNormalizer | None = None,
    ) -> None:
        self._discoverer = discoverer
        self._extractor = extractor
        self._normalizer = normalizer or DataNormalizer()

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        discovery = dict(plan["discovery"])
        raw_properties: list[dict[str, Any]] = []
        market_properties: list[dict[str, Any]] = []
        rejected_properties: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        technical_logs: list[dict[str, Any]] = []
        fatal = False

        try:
            urls = (
                self._discoverer.discover_sync(str(discovery["base_url"]))
                if discovery["mode"] == "fresh"
                else [str(url) for url in discovery["urls"]]
            )
            discovery["urls"] = urls
        except Exception as exception:
            urls = []
            fatal = True
            errors.append({"stage": "discovery", "message": str(exception)})

        profile = dict(plan["extraction_profile"])
        contract = dict(plan["market_data_contract"])
        schemas = dict(profile["schemas"])
        fields = list(contract["fields"])
        required_fields = [
            str(field["name"]) for field in fields if field.get("required") is True
        ]

        for url in urls:
            try:
                extracted, extraction_errors = self._extractor.extract(url, schemas, fields)
            except Exception as exception:
                fatal = True
                errors.append({"stage": "crawl", "url": url, "message": str(exception)})
                break

            raw = dict(extracted or {})
            trace = dict(raw.pop("_extraction_trace", {}))
            raw_index = len(raw_properties)
            raw_properties.append(
                {
                    "url": url,
                    "payload": raw,
                    "extraction_trace": trace,
                    "errors": list(extraction_errors),
                }
            )
            missing = [
                field for field in required_fields if not self._is_meaningful(raw.get(field))
            ]
            if missing:
                rejected_properties.append(
                    {
                        "raw_index": raw_index,
                        "url": url,
                        "payload": raw,
                        "missing_fields": missing,
                        "errors": list(extraction_errors),
                    }
                )
                continue

            normalized = self._normalizer.normalize(raw, fields)
            quality = dict(normalized.pop("_quality", {}))
            normalized_missing = [
                field
                for field in required_fields
                if not self._is_meaningful(normalized.get(field))
            ]
            if normalized_missing:
                rejected_properties.append(
                    {
                        "raw_index": raw_index,
                        "url": url,
                        "payload": raw,
                        "missing_fields": normalized_missing,
                        "errors": ["required field omitted during normalization"],
                    }
                )
                continue

            market_properties.append(
                {
                    "raw_index": raw_index,
                    "payload": normalized,
                    "normalization_warnings": [
                        str(warning) for warning in quality.get("warnings", [])
                    ],
                    "extraction_trace": trace,
                }
            )

        technical_state = "failed" if fatal else "succeeded"
        publishable = technical_state == "succeeded" and bool(market_properties)
        technical_logs.append(
            {
                "level": "error" if fatal else "info",
                "stage": "completed" if not fatal else "failed",
                "message": f"Processed {len(raw_properties)} of {len(urls)} URLs",
                "context": {"error_count": len(errors)},
            }
        )

        return {
            "technical_state": technical_state,
            "result_kind": "partial" if fatal else "full",
            "publishable": publishable,
            "discovery": discovery,
            "raw_properties": raw_properties,
            "market_properties": market_properties,
            "rejected_properties": rejected_properties,
            "errors": errors,
            "artifacts": [
                {
                    "kind": "execution_summary",
                    "payload": {
                        "urls": len(urls),
                        "raw": len(raw_properties),
                        "normalized": len(market_properties),
                        "rejected": len(rejected_properties),
                    },
                }
            ],
            "technical_logs": technical_logs,
        }

    @staticmethod
    def _is_meaningful(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True
