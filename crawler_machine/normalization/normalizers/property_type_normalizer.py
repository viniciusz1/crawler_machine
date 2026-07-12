from __future__ import annotations

from typing import Any

from crawler_machine.catalog import CatalogRepository
from crawler_machine.normalization.result import NormalizationResult


class PropertyTypeNormalizer:
    """Normaliza o campo ``tipo_imovel`` para o vocabulário canônico."""

    def __init__(self, catalog_repository: CatalogRepository):
        self._catalog = catalog_repository

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        catalog_item = self._catalog.find_property_type(text)
        if catalog_item is not None:
            return NormalizationResult(value=catalog_item["name"], is_valid=True)

        return NormalizationResult(
            value=text,
            is_valid=False,
            warnings=[f"tipo_imovel fora do catálogo: {text}"],
        )
