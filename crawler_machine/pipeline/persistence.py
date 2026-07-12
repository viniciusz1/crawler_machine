from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crawler_machine.extermination.exterminator import RejectedRecord
from crawler_machine.output import OutputPath
from crawler_machine.pipeline_helpers import (
    aggregate_rejection_reasons,
    now_iso,
)


def save_discovery_output(
    output: OutputPath, urls: list[str], base_url: str
) -> None:
    _save_json(
        output.discovered,
        {
            "metadata": {
                "base_url": base_url,
                "discovered_at": now_iso(),
                "count": len(urls),
            },
            "urls": urls,
        },
    )


def save_schema_output(
    output: OutputPath, schema: dict[str, Any], sample_url: str | None
) -> None:
    """Persiste o artefato schema.json.

    O schema já deve seguir o formato da cadeia de fallback:
    ``{ metadata, schemas: { xpath, css } }``. O ``sample_url`` é
    normalizado para garantir que o artefato sempre tenha a origem.
    """
    payload = dict(schema)
    metadata = dict(payload.get("metadata", {}))
    metadata.setdefault("sample_url", sample_url or "")
    metadata.setdefault("generated_at", now_iso())
    payload["metadata"] = metadata
    _save_json(output.schema, payload)


def save_raw_output(
    output: OutputPath,
    raw_data: list[dict[str, Any]],
    errors: list[dict[str, Any]],
) -> None:
    _save_json(
        output.raw,
        {
            "metadata": {
                "crawled_at": now_iso(),
                "count": len(raw_data),
                "error_count": len(errors),
            },
            "data": raw_data,
            "errors": errors,
        },
    )


def save_normalized_output(
    output: OutputPath, normalized: list[dict[str, Any]]
) -> None:
    _save_json(
        output.normalized,
        {
            "metadata": {
                "normalized_at": now_iso(),
                "count": len(normalized),
            },
            "data": normalized,
        },
    )


def save_rejected_output(
    output: OutputPath, rejected: list[RejectedRecord]
) -> None:
    _save_json(
        output.rejected,
        {
            "metadata": {
                "rejected_at": now_iso(),
                "count": len(rejected),
            },
            "rejected": [
                {
                    "index": item.index,
                    "record": item.record,
                    "missing_fields": item.missing_fields,
                    "reason": item.reason,
                }
                for item in rejected
            ],
        },
    )


def save_quality_report(
    output: OutputPath,
    rejected: list[RejectedRecord],
    quality_report: dict[str, Any],
) -> None:
    _save_json(
        output.quality_report,
        {
            "metadata": {"generated_at": now_iso()},
            "exterminated_count": len(rejected),
            "extermination_reasons": aggregate_rejection_reasons(rejected),
            **quality_report,
        },
    )


def save_errors_output(
    output: OutputPath, errors: list[dict[str, Any]]
) -> None:
    _save_json(
        output.errors,
        {
            "metadata": {"count": len(errors)},
            "errors": errors,
        },
    )


def _save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
