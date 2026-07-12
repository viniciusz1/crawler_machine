from crawler_machine.normalization.normalizers.area_normalizer import AreaNormalizer


def test_parses_area_with_unit():
    normalizer = AreaNormalizer()
    result = normalizer.normalize("72,5 m²")
    assert result.value == 72.5
    assert result.is_valid is True


def test_rejects_zero_area():
    normalizer = AreaNormalizer()
    result = normalizer.normalize("0 m²")
    assert result.value == 0.0
    assert result.is_valid is False
    assert result.omitted is True


def test_rejects_area_above_threshold():
    normalizer = AreaNormalizer()
    result = normalizer.normalize("999999 m²")
    assert result.value == 999999.0
    assert result.is_valid is False


def test_returns_none_for_empty_value():
    normalizer = AreaNormalizer()
    result = normalizer.normalize(None)
    assert result.value is None
    assert result.omitted is True
