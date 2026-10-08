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


def test_rejects_facebook_tracking_pixel():
    normalizer = ImageNormalizer()

    result = normalizer.normalize(
        "https://www.facebook.com/tr?id=1669136687319144&ev=PageView\n&noscript=1"
    )

    assert result.value is None
    assert result.is_valid is False
    assert result.omitted is True
    assert result.warnings == ["URL de imagem suspeita ou de rastreamento"]


def test_rejects_known_placeholder_image():
    normalizer = ImageNormalizer()

    result = normalizer.normalize("https://cdn.example.com/assets/placeholder.png")

    assert result.value is None
    assert result.is_valid is False
    assert result.omitted is True


def test_does_not_reject_property_filename_containing_logo_sequence():
    normalizer = ImageNormalizer()

    result = normalizer.normalize("https://cdn.example.com/imoveis/catalogo-casa.jpg")

    assert result.value == "https://cdn.example.com/imoveis/catalogo-casa.jpg"
    assert result.is_valid is True


def test_returns_none_for_empty_value():
    normalizer = ImageNormalizer()
    result = normalizer.normalize(None)
    assert result.value is None
    assert result.omitted is True


def test_resolves_relative_image_against_property_url():
    normalizer = ImageNormalizer()

    result = normalizer.normalize(
        "/destaque/320/property.png",
        {"url": "https://agency.example.com/imovel/123"},
    )

    assert result.value == "https://agency.example.com/destaque/320/property.png"
    assert result.is_valid is True
    assert result.warnings == []
