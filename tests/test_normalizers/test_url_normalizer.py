from crawler_machine.normalization.normalizers.url_normalizer import UrlNormalizer


def test_accepts_absolute_url():
    normalizer = UrlNormalizer()
    result = normalizer.normalize("https://example.com/imovel/123")
    assert result.value == "https://example.com/imovel/123"
    assert result.is_valid is True


def test_resolves_relative_url_with_source():
    normalizer = UrlNormalizer()
    result = normalizer.normalize(
        "/imovel/123",
        record={"url": "https://example.com/listagem"},
    )
    assert result.value == "https://example.com/imovel/123"
    assert result.is_valid is True


def test_rejects_invalid_url():
    normalizer = UrlNormalizer()
    result = normalizer.normalize("not-a-url")
    assert result.value is None
    assert result.is_valid is False
    assert result.omitted is True


def test_returns_none_for_empty_value():
    normalizer = UrlNormalizer()
    result = normalizer.normalize("  ")
    assert result.value is None
    assert result.omitted is True
