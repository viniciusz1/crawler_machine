from crawler_machine.extraction.image_candidates import (
    extract_property_image,
    filter_image_candidates,
)


def test_uses_twitter_image_when_open_graph_is_absent():
    html = """
    <html><head>
      <meta name="twitter:image" content="https://cdn.example.com/twitter.jpg" />
    </head><body>
      <img src="https://cdn.example.com/header.jpg" />
    </body></html>
    """

    assert extract_property_image(html) == "https://cdn.example.com/twitter.jpg"


def test_uses_gallery_data_img_before_generic_image():
    html = """
    <html><body>
      <img src="https://cdn.example.com/header.jpg" />
      <div data-img=" https://cdn.example.com/property.jpg "></div>
    </body></html>
    """

    assert extract_property_image(html) == "https://cdn.example.com/property.jpg"


def test_uses_largest_srcset_candidate():
    html = """
    <html><body><picture>
      <source srcset="https://cdn.example.com/small.jpg 400w,
                      https://cdn.example.com/large.jpg 1200w" />
    </picture></body></html>
    """

    assert extract_property_image(html) == "https://cdn.example.com/large.jpg"


def test_ignores_lazy_loaded_logo_element():
    html = """
    <html><body>
      <img alt="Logo da imobiliá" data-src="https://cdn.example.com/brand.jpg" />
      <img src="https://cdn.example.com/property.jpg" />
    </body></html>
    """

    assert extract_property_image(html) == "https://cdn.example.com/property.jpg"


def test_filters_tracking_placeholders_and_duplicates():
    candidates = [
        "https://www.facebook.com/tr?id=123&ev=PageView",
        "https://cdn.example.com/placeholder.png",
        "https://cdn.example.com/property.jpg",
        "https://cdn.example.com/property.jpg",
    ]

    assert filter_image_candidates(candidates) == [
        "https://cdn.example.com/property.jpg"
    ]
