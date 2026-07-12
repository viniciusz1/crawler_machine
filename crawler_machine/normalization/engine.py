from __future__ import annotations

from typing import Any

from crawler_machine.catalog import CatalogRepository
from crawler_machine.config import FieldConfig
from crawler_machine.normalization.coercers import _COERCERS
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
from crawler_machine.normalization.result import NormalizationResult


class DataNormalizer:
    """Orquestra a normalização de registros usando normalizadores específicos por campo."""

    def __init__(
        self,
        catalog_repository: CatalogRepository | None = None,
        city_slug: str | None = None,
        field_normalizers: dict[str, FieldNormalizer] | None = None,
    ):
        self._catalog = catalog_repository
        self._city_slug = city_slug
        self._field_normalizers = field_normalizers or self._build_default_normalizers()

    def _build_default_normalizers(self) -> dict[str, FieldNormalizer]:
        normalizers: dict[str, FieldNormalizer] = {}
        if self._catalog is not None:
            normalizers["tipo_imovel"] = PropertyTypeNormalizer(self._catalog)
            normalizers["cidade"] = CityNormalizer(self._catalog)
            if self._city_slug is not None:
                normalizers["bairro"] = NeighborhoodNormalizer(self._catalog, self._city_slug)

        normalizers["valor"] = ValueNormalizer()
        normalizers["area_util"] = AreaNormalizer()
        normalizers["area_privada"] = AreaNormalizer()
        normalizers["quartos"] = IntegerNormalizer(max_value=50)
        normalizers["suites"] = IntegerNormalizer(max_value=50)
        normalizers["banheiros"] = IntegerNormalizer(max_value=50)
        normalizers["vagas"] = IntegerNormalizer(max_value=50)
        normalizers["sala"] = IntegerNormalizer(max_value=50)
        normalizers["ano"] = YearNormalizer()
        normalizers["url"] = UrlNormalizer()
        normalizers["imagem"] = ImageNormalizer()
        normalizers["detalhes"] = DetailsNormalizer()
        return normalizers

    def normalize(
        self,
        record: dict[str, Any],
        fields: list[FieldConfig] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Normaliza um único registro e anexa metadados de qualidade."""
        normalized: dict[str, Any] = {}
        warnings: list[str] = []

        for key, value in record.items():
            if key.startswith("_"):
                continue

            normalizer = self._field_normalizers.get(key)
            if normalizer is not None:
                result = normalizer.normalize(value, record)
            else:
                result = self._coerce_field(key, value, fields)

            if result.warnings:
                warnings.extend(result.warnings)

            if not result.omitted:
                normalized[key] = result.value

        normalized["_quality"] = {
            "valid": len(warnings) == 0,
            "warnings": warnings,
        }
        return normalized

    def normalize_many(
        self,
        records: list[dict[str, Any]],
        fields: list[FieldConfig] | list[dict[str, Any]] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Normaliza uma lista de registros e gera um relatório de qualidade global."""
        normalized_records = [self.normalize(record, fields) for record in records]

        records_with_issues = [
            index
            for index, record in enumerate(normalized_records)
            if not record["_quality"]["valid"]
        ]

        report = {
            "total_records": len(records),
            "records_with_issues": records_with_issues,
            "strategy_usage": self._aggregate_strategy_usage(records),
            "llm_calls": self._count_llm_calls(records),
        }
        return normalized_records, report

    @staticmethod
    def _aggregate_strategy_usage(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        """Agrega quantos campos cada estratégia forneceu."""
        usage: dict[str, dict[str, int]] = {}
        for record in records:
            trace = record.get("_extraction_trace", {})
            for field, strategy in trace.items():
                usage.setdefault(strategy, {"records": 0, "fields": {}})
                usage[strategy]["fields"][field] = usage[strategy]["fields"].get(field, 0) + 1

        for strategy in usage:
            usage[strategy]["records"] = sum(
                1 for r in records if strategy in r.get("_extraction_trace", {}).values()
            )
        return usage

    @staticmethod
    def _count_llm_calls(records: list[dict[str, Any]]) -> dict[str, int]:
        """Conta chamadas a estratégias que consomem tokens LLM."""
        counts: dict[str, int] = {"fit_markdown_llm": 0, "llm_full_html": 0}
        for record in records:
            trace = record.get("_extraction_trace", {})
            for strategy in counts:
                if strategy in trace.values():
                    counts[strategy] += 1
        return counts

    def _coerce_field(
        self,
        name: str,
        value: Any,
        fields: list[FieldConfig] | list[dict[str, Any]] | None,
    ) -> NormalizationResult:
        coerce_type = self._find_coerce_type(name, fields)
        if coerce_type is None:
            return NormalizationResult(value=value, is_valid=True)

        coercer = _COERCERS.get(coerce_type)
        if coercer is None:
            return NormalizationResult(value=value, is_valid=True)

        coerced = coercer(value)
        if coerced is None and value is not None:
            return NormalizationResult(
                value=None,
                is_valid=False,
                warnings=[f"não foi possível coagir {name} para {coerce_type}"],
                omitted=True,
            )
        return NormalizationResult(value=coerced, is_valid=True)

    def _find_coerce_type(
        self,
        name: str,
        fields: list[FieldConfig] | list[dict[str, Any]] | None,
    ) -> str | None:
        if fields is None:
            return None
        for field in fields:
            field_name = field.name if isinstance(field, FieldConfig) else field.get("name")
            if field_name == name:
                return field.coerce if isinstance(field, FieldConfig) else field.get("coerce")
        return None
