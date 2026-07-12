from unittest.mock import MagicMock

from crawler_machine.config import DomainConfig
from crawler_machine.normalization.engine import DataNormalizer
from crawler_machine.pipeline.normalizer_factory import NormalizerFactory


def test_normalizer_factory_builds_normalizer_without_catalog():
    config = MagicMock(spec=DomainConfig)
    factory = NormalizerFactory(config)

    normalizer = factory.build()

    assert isinstance(normalizer, DataNormalizer)
    assert normalizer._catalog is None


def test_normalizer_factory_builds_normalizer_with_catalog():
    config = MagicMock(spec=DomainConfig)
    catalog = MagicMock()
    factory = NormalizerFactory(config, catalog_repository=catalog)

    normalizer = factory.build()

    assert isinstance(normalizer, DataNormalizer)
    assert normalizer._catalog is catalog
