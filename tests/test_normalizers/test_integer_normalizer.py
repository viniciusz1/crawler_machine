from crawler_machine.normalization.normalizers.integer_normalizer import IntegerNormalizer


def test_parses_integer_from_text():
    normalizer = IntegerNormalizer(max_value=50)
    result = normalizer.normalize("3 (sendo 1 suíte)")
    assert result.value == 3
    assert result.is_valid is True


def test_rejects_negative_value():
    normalizer = IntegerNormalizer(max_value=50)
    result = normalizer.normalize("-1")
    assert result.value == -1
    assert result.is_valid is False
    assert result.omitted is True


def test_rejects_value_above_max():
    normalizer = IntegerNormalizer(max_value=50)
    result = normalizer.normalize("100")
    assert result.value == 100
    assert result.is_valid is False


def test_returns_none_for_empty_value():
    normalizer = IntegerNormalizer(max_value=50)
    result = normalizer.normalize("  ")
    assert result.value is None
    assert result.omitted is True
