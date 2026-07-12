from __future__ import annotations

from typing import Any, Protocol

from crawler_machine.normalization.result import NormalizationResult


class FieldNormalizer(Protocol):
    """Contrato para normalizadores de campos individuais."""

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        """Normaliza um valor isoladamente ou no contexto do registro completo."""
        ...
