from __future__ import annotations

from crawler_machine.config import DomainConfig, FieldConfig
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.normalization.normalizers.area_normalizer import AreaNormalizer
from crawler_machine.normalization.normalizers.city_normalizer import CityNormalizer
from crawler_machine.normalization.normalizers.details_normalizer import DetailsNormalizer
from crawler_machine.normalization.normalizers.image_normalizer import ImageNormalizer
from crawler_machine.normalization.normalizers.integer_normalizer import IntegerNormalizer
from crawler_machine.normalization.normalizers.neighborhood_normalizer import NeighborhoodNormalizer
from crawler_machine.normalization.normalizers.property_type_normalizer import PropertyTypeNormalizer
from crawler_machine.normalization.normalizers.url_normalizer import UrlNormalizer
from crawler_machine.normalization.normalizers.value_normalizer import ValueNormalizer
from crawler_machine.normalization.normalizers.year_normalizer import YearNormalizer
from crawler_machine.normalization.protocol import FieldNormalizer


class NormalizerFactory:
    """Factory para construir o normalizador de registros a partir do domínio."""

    def __init__(
        self,
        config: DomainConfig,
        catalog_repository: "CatalogRepository" | None = None,
        city_slug: str | None = None,
    ):
        self._config = config
        self._catalog_repository = catalog_repository
        self._city_slug = city_slug

    def build(self) -> DataNormalizer:
        return DataNormalizer(
            catalog_repository=self._catalog_repository,
            city_slug=self._city_slug,
            field_normalizers=self._build_field_normalizers(),
        )

    def _build_field_normalizers(self) -> dict[str, FieldNormalizer]:
        """Monta o mapeamento campo -> normalizador usando os campos do domínio."""
        normalizers: dict[str, FieldNormalizer] = {}
        catalog = self._catalog_repository
        city_slug = self._city_slug

        for field in self._iter_fields():
            normalizer = self._normalizer_for(field, catalog, city_slug)
            if normalizer is not None:
                normalizers[field.name] = normalizer

        return normalizers

    def _iter_fields(self) -> list[FieldConfig]:
        """Extrai a lista de FieldConfig de DomainConfig ou de um dict legado."""
        if isinstance(self._config, DomainConfig):
            return self._config.fields

        raw_fields = self._config.get("fields", [])
        return [
            field
            if isinstance(field, FieldConfig)
            else FieldConfig(
                name=field["name"],
                description=field.get("description", ""),
                coerce=field.get("coerce"),
            )
            for field in raw_fields
        ]

    def _normalizer_for(
        self,
        field: FieldConfig,
        catalog: "CatalogRepository" | None,
        city_slug: str | None,
    ) -> FieldNormalizer | None:
        name = field.name
        coerce = field.coerce

        if name == "tipo_imovel" and catalog is not None:
            return PropertyTypeNormalizer(catalog)
        if name == "cidade" and catalog is not None:
            return CityNormalizer(catalog)
        if name == "bairro" and catalog is not None and city_slug is not None:
            return NeighborhoodNormalizer(catalog, city_slug)
        if name == "valor" or coerce == "currency":
            return ValueNormalizer()
        if name in ("area_util", "area_privada") or coerce == "area":
            return AreaNormalizer()
        if coerce == "int":
            return IntegerNormalizer(max_value=50)
        if name == "ano" or coerce == "year":
            return YearNormalizer()
        if name == "url":
            return UrlNormalizer()
        if name == "imagem":
            return ImageNormalizer()
        if name == "detalhes":
            return DetailsNormalizer()

        return None
