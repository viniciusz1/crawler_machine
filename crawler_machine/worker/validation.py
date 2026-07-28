from __future__ import annotations

from typing import Any, Protocol

from crawler_machine.normalization.engine import DataNormalizer


class ProfileExtractor(Protocol):
    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str]]: ...


class RecordNormalizer(Protocol):
    def normalize(
        self,
        record: dict[str, Any],
        fields: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


class ProfileValidationExecutor:
    def __init__(
        self,
        extractor: ProfileExtractor,
        normalizer: RecordNormalizer | None = None,
    ) -> None:
        self._extractor = extractor
        self._normalizer = normalizer or DataNormalizer()

    def run(self, plan: dict[str, Any]) -> dict[str, Any]:
        urls = [str(url) for url in plan["urls"]]
        schemas = dict(plan["schemas"])
        fields = list(plan["fields"])
        required_fields = [
            str(field["name"]) for field in fields if field.get("required") is True
        ]
        field_hits = {field: 0 for field in required_fields}
        records: list[dict[str, Any]] = []
        warnings: list[str] = []
        valid_count = 0
        extraction_policy = plan.get("extraction_policy")

        for url in urls:
            raw_data, extraction_errors = (
                self._extractor.extract(url, schemas, fields, extraction_policy)
                if isinstance(extraction_policy, dict)
                else self._extractor.extract(url, schemas, fields)
            )
            field_presence = {
                field: raw_data is not None and self._is_meaningful(raw_data.get(field))
                for field in required_fields
            }
            for field, present in field_presence.items():
                if present:
                    field_hits[field] += 1

            missing = [field for field, present in field_presence.items() if not present]
            errors = list(extraction_errors)
            if missing:
                errors.append(f"missing required fields: {', '.join(missing)}")

            normalized_data = (
                self._normalizer.normalize(raw_data, fields) if raw_data is not None else None
            )
            quality = normalized_data.get("_quality", {}) if normalized_data else {}
            normalization_warnings = [str(item) for item in quality.get("warnings", [])]
            warnings.extend(normalization_warnings)
            is_valid = (
                raw_data is not None
                and not missing
                and bool(quality.get("valid", False))
            )
            if is_valid:
                valid_count += 1

            records.append(
                {
                    "url": url,
                    "raw_data": raw_data,
                    "normalized_data": normalized_data,
                    "errors": errors,
                    "field_presence": field_presence,
                    "is_valid": is_valid,
                }
            )

        sampled_count = len(urls)
        valid_ratio = round(valid_count / sampled_count, 4) if sampled_count else 0.0
        coverage = {
            field: round(hits / sampled_count, 4) if sampled_count else 0.0
            for field, hits in field_hits.items()
        }
        blocking_failures: list[str] = []
        if sampled_count == 0:
            blocking_failures.append("no_urls_sampled")
        if valid_count == 0:
            blocking_failures.append("no_valid_records")

        thresholds = plan.get("thresholds", {})
        valid_threshold = float(thresholds.get("valid_ratio", 0.80))
        coverage_threshold = float(thresholds.get("required_field_coverage", 0.90))
        eligible = (
            valid_ratio >= valid_threshold
            and all(value >= coverage_threshold for value in coverage.values())
            and blocking_failures == []
        )

        return {
            "sampled_url_count": sampled_count,
            "valid_record_count": valid_count,
            "valid_ratio": valid_ratio,
            "required_field_coverage": coverage,
            "blocking_failures": blocking_failures,
            "warnings": list(dict.fromkeys(warnings)),
            "eligible": eligible,
            "records": records,
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
