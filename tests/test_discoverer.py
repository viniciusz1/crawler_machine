import pytest

from crawler_machine.discoverer import URLDiscoverer


class FakeMapper:
    def __init__(self, results: list[dict]):
        self.results = results

    async def scan(self, url: str, **kwargs: object) -> list[dict]:
        return self.results


class FakeSitemapFetcher:
    def __init__(self, urls: list[str]):
        self.urls = urls

    async def fetch(self, base_url: str) -> list[str]:
        return self.urls


@pytest.fixture
def mapper_results():
    return [
        {"url": "https://example.com/imovel/1", "status": "valid"},
        {"url": "https://example.com/imovel/2", "status": "valid"},
        {"url": "https://example.com/outra", "status": "valid"},
    ]


def test_discoverer_returns_all_urls_when_filter_disabled(mapper_results):
    mapper = FakeMapper(mapper_results)
    discoverer = URLDiscoverer(mapper=mapper, max_urls=10, listing_patterns=[])

    urls = discoverer.discover_sync("https://example.com")

    assert urls == [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
        "https://example.com/outra",
    ]


def test_discoverer_filters_urls_by_listing_patterns(mapper_results):
    mapper = FakeMapper(mapper_results)
    discoverer = URLDiscoverer(mapper=mapper, max_urls=10, listing_patterns=[r"/imovel/"])

    urls = discoverer.discover_sync("https://example.com")

    assert urls == [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ]


def test_discoverer_respects_max_urls(mapper_results):
    mapper = FakeMapper(mapper_results)
    discoverer = URLDiscoverer(mapper=mapper, max_urls=2, listing_patterns=[])

    urls = discoverer.discover_sync("https://example.com")

    assert len(urls) == 2
    assert urls == [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ]


def test_discoverer_skips_entries_without_url():
    mapper = FakeMapper([
        {"url": "https://example.com/imovel/1", "status": "valid"},
        {"status": "valid"},
        {"url": None, "status": "valid"},
    ])
    discoverer = URLDiscoverer(mapper=mapper, max_urls=10, listing_patterns=[])

    urls = discoverer.discover_sync("https://example.com")

    assert urls == ["https://example.com/imovel/1"]


def test_discoverer_passes_the_operation_policy_to_the_mapper(mapper_results):
    class RecordingMapper(FakeMapper):
        async def scan(self, url: str, **kwargs: object) -> list[dict]:
            self.policy = kwargs
            return self.results

    mapper = RecordingMapper(mapper_results)
    discoverer = URLDiscoverer(mapper=mapper, max_urls=500, listing_patterns=[])

    discoverer.discover_sync("https://example.com", {"sources": ["sitemap", "robots"], "max_urls": 20, "include_subdomains": False})

    assert mapper.policy == {"source": "sitemap+robots", "max_urls": 20, "include_subdomains": False}


def test_discoverer_uses_sitemap_fallback_when_mapper_returns_no_urls():
    sitemap_urls = [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ]
    discoverer = URLDiscoverer(
        mapper=FakeMapper([]),
        sitemap_fetcher=FakeSitemapFetcher(sitemap_urls),
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"sources": ["sitemap"]},
    )

    assert urls == sitemap_urls
