from crawler_machine.normalization.normalizers.details_normalizer import DetailsNormalizer


def test_cleans_description():
    normalizer = DetailsNormalizer()
    result = normalizer.normalize("  Apartamento   bem localizado  ")
    assert result.value == "Apartamento bem localizado"
    assert result.is_valid is True


def test_warns_short_description():
    normalizer = DetailsNormalizer()
    result = normalizer.normalize("abc")
    assert result.value == "abc"
    assert result.is_valid is True
    assert any("curta" in w for w in result.warnings)


def test_returns_none_for_empty_value():
    normalizer = DetailsNormalizer()
    result = normalizer.normalize("   ")
    assert result.value is None
    assert result.omitted is True
