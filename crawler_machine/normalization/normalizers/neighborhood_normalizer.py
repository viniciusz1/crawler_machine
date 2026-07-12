from __future__ import annotations

from typing import Any

from crawler_machine.catalog import CatalogRepository
from crawler_machine.normalization.result import NormalizationResult


class NeighborhoodNormalizer:
    """Normaliza o campo ``bairro`` para o vocabulário canônico de uma cidade."""

    def __init__(self, catalog_repository: CatalogRepository, city_slug: str):
        self._catalog = catalog_repository
        self._city_slug = city_slug

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        catalog_item = self._catalog.find_neighborhood(self._city_slug, text)
        if catalog_item is not None:
            return NormalizationResult(value=catalog_item["name"], is_valid=True)

        return NormalizationResult(
            value=text,
            is_valid=False,
            warnings=[f"bairro fora do catálogo: {text}"],
        )
