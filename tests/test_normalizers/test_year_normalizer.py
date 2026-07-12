from datetime import datetime

from crawler_machine.normalization.normalizers.year_normalizer import YearNormalizer


def test_parses_year():
    normalizer = YearNormalizer()
    result = normalizer.normalize("2020")
    assert result.value == 2020
    assert result.is_valid is True


def test_rejects_year_too_old():
    normalizer = YearNormalizer()
    result = normalizer.normalize("1700")
    assert result.value == 1700
    assert result.is_valid is False
    assert result.omitted is True


def test_rejects_year_in_the_future():
    normalizer = YearNormalizer()
    future_year = datetime.now().year + 10
    result = normalizer.normalize(str(future_year))
    assert result.value == future_year
    assert result.is_valid is False


def test_returns_none_for_empty_value():
    normalizer = YearNormalizer()
    result = normalizer.normalize(None)
    assert result.value is None
    assert result.omitted is True
