from crawler_machine.normalization.normalizers.image_normalizer import ImageNormalizer


def test_accepts_image_url():
    normalizer = ImageNormalizer()
    result = normalizer.normalize("https://example.com/img.jpg")
    assert result.value == "https://example.com/img.jpg"
    assert result.is_valid is True


def test_rejects_invalid_image_url():
    normalizer = ImageNormalizer()
    result = normalizer.normalize("javascript:alert(1)")
    assert result.value is None
    assert result.is_valid is False
    assert result.omitted is True


def test_returns_none_for_empty_value():
    normalizer = ImageNormalizer()
    result = normalizer.normalize(None)
    assert result.value is None
    assert result.omitted is True
