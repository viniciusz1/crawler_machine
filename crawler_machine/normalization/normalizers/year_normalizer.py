from __future__ import annotations

from datetime import datetime
from typing import Any

from crawler_machine.normalization.result import NormalizationResult
from crawler_machine.normalization.coercers import extract_first_number


class YearNormalizer:
    """Normaliza e valida o campo ``ano`` de construção."""

    MIN_YEAR = 1800

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
                warnings=[f"ano não reconhecido: {text}"],
                omitted=True,
            )

        year = int(parsed)
        max_year = datetime.now().year + 2

        if year < self.MIN_YEAR:
            return NormalizationResult(
                value=year,
                is_valid=False,
                warnings=[f"ano abaixo do limite permitido: {year}"],
                omitted=True,
            )

        if year > max_year:
            return NormalizationResult(
                value=year,
                is_valid=False,
                warnings=[f"ano acima do limite permitido: {year}"],
                omitted=True,
            )

        return NormalizationResult(value=year, is_valid=True)
