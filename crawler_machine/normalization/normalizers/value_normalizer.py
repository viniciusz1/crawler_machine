from __future__ import annotations

from typing import Any

from crawler_machine.normalization.result import NormalizationResult
from crawler_machine.normalization.coercers import extract_first_number


class ValueNormalizer:
    """Normaliza e valida o campo ``valor`` monetário."""

    MAX_VALUE = 100_000_000

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        parsed = extract_first_number(text)
        if parsed is None:
            return NormalizationResult(
                value=None,
                is_valid=False,
                warnings=[f"valor não reconhecido: {text}"],
                omitted=True,
            )

        if parsed <= 0:
            return NormalizationResult(
                value=parsed,
                is_valid=False,
                warnings=[f"valor deve ser maior que zero: {parsed}"],
                omitted=True,
            )

        if parsed > self.MAX_VALUE:
            return NormalizationResult(
                value=parsed,
                is_valid=False,
                warnings=[f"valor acima do limite permitido: {parsed}"],
            )

        return NormalizationResult(value=parsed, is_valid=True)
