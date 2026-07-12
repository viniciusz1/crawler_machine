from __future__ import annotations

import re
from typing import Any


FIELD_RENAME_MAP: dict[str, str] = {
    "tipo_imovel": "tipo",
    "url": "link_imovel",
    "detalhes": "descricao",
    "area_util": "area",
    "ano": "ano_construcao",
}


def rename_fields(record: dict[str, Any]) -> dict[str, Any]:
    """Mapeia nomes de campos do crawler para nomes de colunas do banco."""
    renamed: dict[str, Any] = {}
    for key, value in record.items():
        renamed[FIELD_RENAME_MAP.get(key, key)] = value
    return renamed


def to_boolean(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"true", "sim", "yes", "1", "s"}:
        return True
    if text in {"false", "não", "nao", "no", "0", "n"}:
        return False
    return None


def to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text == "":
        return None
    cleaned = re.sub(r"[^\d,\.]", "", text)
    if cleaned == "":
        return None
    try:
        if "," in cleaned and "." in cleaned:
            last_comma = cleaned.rfind(",")
            last_dot = cleaned.rfind(".")
            if last_comma > last_dot:
                cleaned = cleaned.replace(".", "").replace(",", ".")
            else:
                cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            if cleaned.count(",") > 1:
                cleaned = cleaned.replace(",", "")
            else:
                cleaned = cleaned.replace(",", ".")
        return float(cleaned)
    except ValueError:
        return None


def to_int(value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    text = str(value).strip()
    if text == "":
        return None
    match = re.search(r"\d+", text)
    if not match:
        return None
    return int(match.group(0))


def coerce_for_column(value: Any, column: str) -> Any:
    from crawler_machine.sink.columns import BOOLEAN_FIELDS

    if column in BOOLEAN_FIELDS:
        return to_boolean(value)
    if column in {"valor", "area"}:
        return to_float(value)
    if column in {"quartos", "suites", "banheiros", "vagas", "ano_construcao"}:
        return to_int(value)
    if value is None:
        return None
    return str(value).strip() if str(value).strip() != "" else None
