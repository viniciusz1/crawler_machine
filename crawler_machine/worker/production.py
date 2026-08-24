from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol
from urllib.parse import urlparse

from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.worker.validation import ProfileExtractor, RecordNormalizer


class SynchronousDiscoverer(Protocol):
    def discover_sync(
        self,
        base_url: str,
        policy: dict[str, Any] | None = None,
    ) -> list[str]: ...


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

    def run(
        self,
        plan: dict[str, Any],
        should_cancel: Callable[[], bool] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
    ) -> dict[str, Any]:
        discovery = dict(plan["discovery"])
        raw_properties: list[dict[str, Any]] = []
        market_properties: list[dict[str, Any]] = []
        rejected_properties: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        technical_logs: list[dict[str, Any]] = []
        fatal = False
        cancelled = False
        cancellation_check = should_cancel or (lambda: False)
        progress_callback = on_progress or (lambda _processed, _total: None)

        try:
            discovery_policy = plan.get("discovery_policy")
            if discovery["mode"] == "fresh":
                urls = (
                    self._discoverer.discover_sync(
                        str(discovery["base_url"]),
                        discovery_policy,
                    )
                    if isinstance(discovery_policy, dict)
                    else self._discoverer.discover_sync(
                        str(discovery["base_url"])
                    )
                )
            else:
                urls = [str(url) for url in discovery["urls"]]
            discovery["urls"] = urls
        except Exception as exception:
            urls = []
            fatal = True
            errors.append({"stage": "discovery", "message": str(exception)})

        profile = dict(plan["extraction_profile"])
        urls = self._urls_matching_approved_detail_shape(urls, profile)
        discovery["urls"] = urls
        contract = dict(plan["market_data_contract"])
        schemas = dict(profile["schemas"])
        fields = list(contract["fields"])
        extraction_policy = self._extraction_policy(plan, profile)
        required_fields = [
            str(field["name"]) for field in fields if field.get("required") is True
        ]
        extracted_rows: list[tuple[str, dict[str, Any] | None, list[str]]] = []
        batch_extract = getattr(self._extractor, "extract_many", None)

        if callable(batch_extract):
            if urls and cancellation_check():
                cancelled = True
            elif urls:
                try:
                    batch_results = (
                        batch_extract(urls, schemas, fields, extraction_policy)
                        if extraction_policy is not None
                        else batch_extract(urls, schemas, fields)
                    )
                    if len(batch_results) != len(urls):
                        raise RuntimeError(
                            "Profile extractor returned an invalid result count"
                        )
                    extracted_rows.extend(
                        (url, extracted, extraction_errors)
                        for url, (extracted, extraction_errors) in zip(
                            urls,
                            batch_results,
                            strict=True,
                        )
                    )
                except Exception as exception:
                    fatal = True
                    errors.append({"stage": "crawl", "message": str(exception)})
        else:
            for url in urls:
                if cancellation_check():
                    cancelled = True
                    break
                try:
                    extracted, extraction_errors = (
                        self._extractor.extract(
                            url,
                            schemas,
                            fields,
                            extraction_policy,
                        )
                        if extraction_policy is not None
                        else self._extractor.extract(url, schemas, fields)
                    )
                    extracted_rows.append((url, extracted, extraction_errors))
                except Exception as exception:
                    fatal = True
                    errors.append(
                        {"stage": "crawl", "url": url, "message": str(exception)}
                    )
                    break

        for url, extracted, extraction_errors in extracted_rows:
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
                progress_callback(len(raw_properties), len(urls))
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
                progress_callback(len(raw_properties), len(urls))
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
            progress_callback(len(raw_properties), len(urls))

        technical_state = "cancelled" if cancelled else ("failed" if fatal else "succeeded")
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
            "result_kind": "partial" if fatal or cancelled else "full",
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

    @staticmethod
    def _urls_matching_approved_detail_shape(
        urls: list[str],
        profile: dict[str, Any],
    ) -> list[str]:
        parameters = profile.get("parameters")
        sample_url = profile.get("sample_url")
        if not isinstance(sample_url, str) and isinstance(parameters, dict):
            sample_url = parameters.get("sample_url")
        if not isinstance(sample_url, str):
            return urls

        detail_markers = {"imovel", "property", "listing", "detalhe", "detalhes"}
        sample_segments = ProductionCrawlExecutor._path_segments(sample_url)
        marker = next(
            (segment for segment in sample_segments if segment in detail_markers),
            None,
        )
        if marker is None:
            return urls

        matching = [
            url
            for url in urls
            if marker in ProductionCrawlExecutor._path_segments(url)
        ]
        return matching or urls

    @staticmethod
    def _path_segments(url: str) -> tuple[str, ...]:
        return tuple(
            segment.lower()
            for segment in urlparse(url).path.split("/")
            if segment
        )

    @staticmethod
    def _extraction_policy(
        plan: dict[str, Any],
        profile: dict[str, Any],
    ) -> dict[str, Any] | None:
        policy = plan.get("extraction_policy")
        if isinstance(policy, dict):
            return dict(policy)

        parameters = profile.get("parameters")
        nested_policy = (
            parameters.get("extraction_policy")
            if isinstance(parameters, dict)
            else None
        )
        if isinstance(nested_policy, dict):
            return dict(nested_policy)

        strategies = profile.get("strategies")
        if isinstance(strategies, list) and strategies:
            return {"source": "extraction_profile", "strategies": list(strategies)}
        return None
