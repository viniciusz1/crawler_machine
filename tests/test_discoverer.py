import asyncio

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


class HangingMapper:
    async def scan(self, url: str, **kwargs: object) -> list[dict]:
        await asyncio.Event().wait()
        return []


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


def test_discoverer_recognizes_numeric_and_query_string_listing_urls():
    discoverer = URLDiscoverer(
        mapper=FakeMapper([
            {"url": "https://macro.example.com/2494"},
            {"url": "https://achave.example.com/detalhes_vd.php?imovel=9003"},
            {"url": "https://achave.example.com/detalhes_loc.php?imovel=3025"},
            {"url": "https://macro.example.com/contato"},
        ]),
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"sources": ["homepage"]},
    )

    assert urls == [
        "https://macro.example.com/2494",
        "https://achave.example.com/detalhes_vd.php?imovel=9003",
        "https://achave.example.com/detalhes_loc.php?imovel=3025",
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


def test_discoverer_applies_catalog_policy_configuration():
    class RecordingMapper(FakeMapper):
        async def scan(self, url: str, **kwargs: object) -> list[dict]:
            self.policy = kwargs
            return self.results

    mapper = RecordingMapper([
        {"url": "https://example.com/imovel/1"},
        {"url": "https://example.com/imovel/2"},
        {"url": "https://example.com/imovel/3"},
    ])
    discoverer = URLDiscoverer(mapper=mapper, max_urls=2, listing_patterns=[])

    urls = discoverer.discover_sync(
        "https://example.com",
        {
            "sources": ["homepage"],
            "configuration": {
                "max_urls": 3,
                "include_subdomains": False,
            },
        },
    )

    assert urls == [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
        "https://example.com/imovel/3",
    ]
    assert mapper.policy == {
        "source": "homepage",
        "max_urls": 3,
        "include_subdomains": False,
    }


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


def test_discoverer_uses_sitemap_fallback_when_mapper_has_no_listing_urls():
    discoverer = URLDiscoverer(
        mapper=FakeMapper([
            {"url": "https://example.com/"},
            {"url": "https://example.com/contato"},
        ]),
        sitemap_fetcher=FakeSitemapFetcher([
            "https://example.com/imovel/apartamento-centro.html",
            "https://example.com/empresa",
        ]),
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"sources": ["sitemap"]},
    )

    assert urls == ["https://example.com/imovel/apartamento-centro.html"]


def test_discoverer_merges_sitemap_urls_with_other_selected_sources():
    discoverer = URLDiscoverer(
        mapper=FakeMapper([
            {"url": "https://example.com/imovel/mapper-1"},
        ]),
        sitemap_fetcher=FakeSitemapFetcher([
            "https://example.com/imovel/mapper-1",
            "https://example.com/imovel/sitemap-2",
        ]),
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"sources": ["sitemap", "cc"]},
    )

    assert urls == [
        "https://example.com/imovel/mapper-1",
        "https://example.com/imovel/sitemap-2",
    ]


def test_discoverer_keeps_sitemap_results_when_mapper_times_out():
    discoverer = URLDiscoverer(
        mapper=HangingMapper(),
        sitemap_fetcher=FakeSitemapFetcher([
            "https://example.com/imovel/sitemap-1",
        ]),
        mapper_timeout_seconds=0.01,
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"sources": ["sitemap", "homepage"]},
    )

    assert urls == ["https://example.com/imovel/sitemap-1"]


class FakePlaywrightDiscoverer:
    def __init__(self, urls: list[str]):
        self.urls = urls
        self.calls: list[tuple[str, dict | None]] = []

    async def discover(self, base_url: str, policy: dict | None = None) -> list[str]:
        self.calls.append((base_url, policy))
        return list(self.urls)


class ExplodingMapper:
    async def scan(self, url: str, **kwargs: object) -> list[dict]:
        raise AssertionError("DomainMapper should not be called when only playwright is selected")


def test_discoverer_uses_playwright_strategy_when_selected_in_policy():
    pw_discoverer = FakePlaywrightDiscoverer([
        "https://example.com/imovel/pw-1",
        "https://example.com/imovel/pw-2",
    ])
    discoverer = URLDiscoverer(
        mapper=ExplodingMapper(),
        sitemap_fetcher=FakeSitemapFetcher(["https://example.com/imovel/sitemap-ignored"]),
        playwright_discoverer=pw_discoverer,
    )

    urls = discoverer.discover_sync(
        "https://example.com/imoveis",
        {"strategies": ["playwright"], "configuration": {"max_urls": 10}},
    )

    assert urls == [
        "https://example.com/imovel/pw-1",
        "https://example.com/imovel/pw-2",
    ]
    assert len(pw_discoverer.calls) == 1
    assert pw_discoverer.calls[0][0] == "https://example.com/imoveis"


def test_discoverer_merges_playwright_and_sitemap_strategies_without_passing_playwright_to_domain_mapper():
    class RecordingMapper(FakeMapper):
        async def scan(self, url: str, **kwargs: object) -> list[dict]:
            self.policy = kwargs
            return self.results

    mapper = RecordingMapper([{"url": "https://example.com/imovel/mapper-1"}])
    pw_discoverer = FakePlaywrightDiscoverer([
        "https://example.com/imovel/pw-1",
        "https://example.com/imovel/sitemap-1",
    ])
    discoverer = URLDiscoverer(
        mapper=mapper,
        sitemap_fetcher=FakeSitemapFetcher(["https://example.com/imovel/sitemap-1"]),
        playwright_discoverer=pw_discoverer,
    )

    urls = discoverer.discover_sync(
        "https://example.com",
        {"strategies": ["playwright", "sitemap"]},
    )

    assert urls == [
        "https://example.com/imovel/mapper-1",
        "https://example.com/imovel/sitemap-1",
        "https://example.com/imovel/pw-1",
    ]
    assert mapper.policy == {"source": "sitemap"}


def test_discoverer_uses_default_strategies_when_no_policy_is_passed():
    pw_discoverer = FakePlaywrightDiscoverer(["https://example.com/imovel/pw-default"])
    discoverer = URLDiscoverer(
        mapper=ExplodingMapper(),
        sitemap_fetcher=FakeSitemapFetcher([]),
        playwright_discoverer=pw_discoverer,
        default_strategies=["playwright"],
    )

    urls = discoverer.discover_sync("https://example.com/imoveis")

    assert urls == ["https://example.com/imovel/pw-default"]


