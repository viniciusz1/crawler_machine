from __future__ import annotations

import re
from typing import Any

from crawler_machine.normalization.result import NormalizationResult


class DetailsNormalizer:
    """Limpa e valida o campo de descrição/detalhes do imóvel."""

    MIN_LENGTH = 10

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        cleaned = re.sub(r"\s+", " ", text)
        warnings: list[str] = []
        if len(cleaned) < self.MIN_LENGTH:
            warnings.append(f"descrição muito curta ({len(cleaned)} caracteres)")

        return NormalizationResult(value=cleaned, is_valid=True, warnings=warnings)
