from __future__ import annotations

import re
from typing import Any


def extract_first_number(text: Any) -> float | None:
    """Extrai o primeiro número encontrado em uma string.

    Aceita separadores brasileiros e internacionais:
      - "72 ~ 79 m²"        -> 72.0
      - "3 (sendo 1 suíte)" -> 3.0
      - "1.234,56"          -> 1234.56
      - "1,234.56"          -> 1234.56
    """
    if text is None:
        return None

    text = str(text).strip()
    if not text:
        return None

    match = re.search(r"[\d.,]+", text)
    if not match:
        return None

    return parse_number(match.group(0))


def parse_number(raw: str) -> float | None:
    """Converte uma string numérica (com pontos/vírgulas) para float."""
    raw = raw.strip()
    if not raw:
        return None

    has_comma = "," in raw
    has_dot = "." in raw

    if has_comma and has_dot:
        last_comma = raw.rfind(",")
        last_dot = raw.rfind(".")
        if last_comma > last_dot:
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif has_comma and not has_dot:
        raw = _normalize_single_separator(raw, ",")
    elif has_dot and not has_comma:
        raw = _normalize_single_separator(raw, ".")

    try:
        return float(raw)
    except ValueError:
        return None


def _normalize_single_separator(raw: str, separator: str) -> str:
    """Distingue agrupamento de milhares de uma fração decimal.

    Imobiliárias brasileiras frequentemente omitem os centavos e publicam
    valores como ``329.000``. Um único separador seguido por três dígitos deve,
    portanto, ser tratado como agrupamento, enquanto ``72,5`` continua decimal.
    """
    groups = raw.split(separator)
    is_grouped_thousands = (
        len(groups) > 1
        and all(group.isdigit() for group in groups)
        and all(len(group) == 3 for group in groups[1:])
    )
    if is_grouped_thousands:
        return "".join(groups)
    if len(groups) == 2:
        return ".".join(groups)
    return raw


def coerce_int(value: Any) -> int | None:
    """Extrai o primeiro número e retorna como int."""
    number = extract_first_number(value)
    if number is None:
        return None
    return int(number)


def coerce_float(value: Any) -> float | None:
    """Extrai o primeiro número e retorna como float."""
    return extract_first_number(value)


def coerce_currency(value: Any) -> float | None:
    """Extrai o primeiro valor monetário e retorna como float."""
    return extract_first_number(value)


def coerce_string(value: Any) -> str | None:
    """Garante que o valor seja uma string limpa."""
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def coerce_boolean(value: Any) -> bool | None:
    """Converte um valor para booleano."""
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


_COERCERS: dict[str, Any] = {
    "int": coerce_int,
    "float": coerce_float,
    "currency": coerce_currency,
    "string": coerce_string,
    "text": coerce_string,
    "boolean": coerce_boolean,
}
