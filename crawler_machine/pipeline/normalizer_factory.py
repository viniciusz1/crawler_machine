from __future__ import annotations

from crawler_machine.config import DomainConfig
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.pipeline.protocols import Sink


class NormalizerFactory:
    """Factory para construir o normalizador de registros."""

    def __init__(
        self,
        config: DomainConfig,
        catalog_repository: "CatalogRepository" | None = None,
    ):
        self._config = config
        self._catalog_repository = catalog_repository

    def build(self) -> DataNormalizer:
        return DataNormalizer(catalog_repository=self._catalog_repository)
