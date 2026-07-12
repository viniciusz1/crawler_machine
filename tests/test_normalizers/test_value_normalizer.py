import pytest

from crawler_machine.normalization.normalizers.value_normalizer import ValueNormalizer


def test_parses_brazilian_currency():
    normalizer = ValueNormalizer()
    result = normalizer.normalize("R$ 450.000,00")
    assert result.value == 450000.0
    assert result.is_valid is True


def test_rejects_zero_value():
    normalizer = ValueNormalizer()
    result = normalizer.normalize("R$ 0,00")
    assert result.value == 0.0
    assert result.is_valid is False
    assert result.omitted is True


def test_rejects_value_above_threshold():
    normalizer = ValueNormalizer()
    result = normalizer.normalize("R$ 999.999.999,00")
    assert result.value == 999_999_999.0
    assert result.is_valid is False


def test_returns_none_for_empty_value():
    normalizer = ValueNormalizer()
    result = normalizer.normalize("")
    assert result.value is None
    assert result.omitted is True
