from unittest.mock import MagicMock

from crawler_machine.config import DomainConfig, FieldConfig
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.normalization.normalizers.value_normalizer import ValueNormalizer
from crawler_machine.pipeline.normalizer_factory import NormalizerFactory


def test_normalizer_factory_builds_normalizer_without_catalog():
    config = MagicMock(spec=DomainConfig)
    config.fields = []
    factory = NormalizerFactory(config)

    normalizer = factory.build()

    assert isinstance(normalizer, DataNormalizer)
    assert normalizer._catalog is None
    assert normalizer._field_normalizers == {}


def test_normalizer_factory_builds_normalizer_with_catalog():
    config = MagicMock(spec=DomainConfig)
    config.fields = []
    catalog = MagicMock()
    factory = NormalizerFactory(config, catalog_repository=catalog)

    normalizer = factory.build()

    assert isinstance(normalizer, DataNormalizer)
    assert normalizer._catalog is catalog


def test_normalizer_factory_uses_config_fields_to_pick_normalizers():
    config = MagicMock(spec=DomainConfig)
    config.fields = [
        FieldConfig(name="valor", description="Valor", coerce="currency"),
        FieldConfig(name="quartos", description="Quartos", coerce="int"),
    ]

    normalizer = NormalizerFactory(config).build()

    assert "valor" in normalizer._field_normalizers
    assert "quartos" in normalizer._field_normalizers
    assert isinstance(normalizer._field_normalizers["valor"], ValueNormalizer)


def test_normalizer_factory_uses_catalog_for_semantic_fields():
    catalog = MagicMock()
    config = MagicMock(spec=DomainConfig)
    config.fields = [FieldConfig(name="tipo_imovel", description="Tipo")]

    normalizer = NormalizerFactory(config, catalog_repository=catalog).build()

    assert "tipo_imovel" in normalizer._field_normalizers
