from __future__ import annotations

import json
from typing import Any

from crawler_machine.sink.coercion import coerce_for_column, rename_fields


def build_raw_rows(
    run_id: int,
    raw_properties: list[dict[str, Any]],
    raw_property_columns: list[str],
) -> list[tuple]:
    rows: list[tuple] = []
    for record in raw_properties:
        row: list[Any] = [run_id]
        payload = dict(record)
        for column in raw_property_columns[1:]:
            if column == "source_url":
                row.append(record.get("url"))
            elif column == "external_id":
                row.append(record.get("external_id"))
            elif column == "raw_payload":
                row.append(json.dumps(payload))
            else:
                value = record.get(column)
                row.append(str(value) if value is not None else None)
        rows.append(tuple(row))
    return rows


def build_market_rows(
    run_id: int,
    normalized_properties: list[dict[str, Any]],
    raw_ids: list[int],
    source_name: str,
    market_property_columns: list[str],
) -> list[tuple]:
    rows: list[tuple] = []
    for index, record in enumerate(normalized_properties):
        renamed = rename_fields(record)
        quality = record.get("_quality", {})
        quality_status = "valid" if quality.get("valid", True) else "invalid"
        quality_metadata = quality

        row: list[Any] = [run_id]
        raw_property_id = raw_ids[index] if index < len(raw_ids) else None
        row.append(raw_property_id)
        row.append(record.get("url"))

        for column in market_property_columns[3:]:
            if column == "imobiliaria":
                value = renamed.get("imobiliaria") or source_name
            elif column == "quality_status":
                value = quality_status
            elif column == "quality_metadata":
                value = json.dumps(quality_metadata)
            else:
                value = renamed.get(column)
            row.append(coerce_for_column(value, column))
        rows.append(tuple(row))
    return rows
