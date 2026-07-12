from __future__ import annotations

from typing import Any

from crawler_machine.normalization.result import NormalizationResult
from crawler_machine.normalization.coercers import extract_first_number


class IntegerNormalizer:
    """Normaliza e valida campos inteiros com limite superior."""

    def __init__(self, max_value: int):
        self._max_value = max_value

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        is_negative = text.startswith("-")
        parsed = extract_first_number(text)
        if parsed is None:
            return NormalizationResult(
                value=None,
                is_valid=False,
                warnings=[f"número não reconhecido: {text}"],
                omitted=True,
            )

        integer_value = -int(parsed) if is_negative else int(parsed)

        if integer_value < 0:
            return NormalizationResult(
                value=integer_value,
                is_valid=False,
                warnings=[f"valor não pode ser negativo: {integer_value}"],
                omitted=True,
            )

        if integer_value > self._max_value:
            return NormalizationResult(
                value=integer_value,
                is_valid=False,
                warnings=[f"valor acima do limite permitido: {integer_value}"],
            )

        return NormalizationResult(value=integer_value, is_valid=True)
