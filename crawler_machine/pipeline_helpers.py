from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from crawler_machine.extermination.exterminator import RejectedRecord


def now_iso() -> str:
    """Retorna o instante atual no formato ISO 8601 (UTC)."""
    return datetime.now(timezone.utc).isoformat()


def detect_schema_type(schema: dict[str, Any]) -> str:
    """Detecta se o schema usa XPath ou CSS baseado nos seletores."""
    selectors = [schema.get("baseSelector", "")]
    for field in schema.get("fields", []):
        if "selector" in field:
            selectors.append(field["selector"])

    if any(
        isinstance(selector, str)
        and (selector.startswith("//") or selector.startswith(".//"))
        for selector in selectors
    ):
        return "XPATH"
    return "CSS"


def aggregate_rejection_reasons(
    rejected: list[RejectedRecord],
) -> dict[str, int]:
    """Agrega quantos registros foram eliminados por cada campo obrigatório."""
    reasons: dict[str, int] = {}
    for item in rejected:
        for field in item.missing_fields:
            reasons[field] = reasons.get(field, 0) + 1
    return reasons
