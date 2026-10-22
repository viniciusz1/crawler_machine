from __future__ import annotations

import asyncio
import gzip
import logging
import re
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

from crawler_machine.playwright_discoverer import (
    _DEFAULT_PROPERTY_PATTERNS,
    PlaywrightListingDiscoverer,
)

logger = logging.getLogger(__name__)

_PLAYWRIGHT_STRATEGIES = {"playwright", "playwright_listing", "listing_pagination"}
_DOMAIN_MAPPER_SOURCES = {
    "sitemap",
    "cc",
    "wayback",
    "crt",
    "probe",
    "robots",
    "feed",
    "homepage",
}

_DEFAULT_LISTING_PATTERNS = list(_DEFAULT_PROPERTY_PATTERNS)


class URLMapper(Protocol):
    """Porta para descoberta de URLs."""

    async def scan(self, url: str, **kwargs: Any) -> list[dict[str, Any]]: ...


class SitemapFetcher(Protocol):
    async def fetch(self, base_url: str) -> list[str]: ...


class HttpSitemapFetcher:
    """Fetches sitemap URLs without relying on a HEAD probe."""

    async def fetch(self, base_url: str) -> list[str]:
        origin = self._origin(base_url)
        sitemap_urls = await self._sitemap_urls_from_robots(origin)
        sitemap_urls.extend(
            urljoin(origin, path)
            for path in ("/sitemap.xml", "/sitemap_index.xml")
        )

        discovered: list[str] = []
        visited: set[str] = set()
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15,
            headers={"User-Agent": "ia-imob-crawler/1.0"},
        ) as client:
            pending = list(dict.fromkeys(sitemap_urls))
            while pending:
                sitemap_url = pending.pop(0)
                if sitemap_url in visited:
                    continue
                visited.add(sitemap_url)
                try:
                    response = await client.get(sitemap_url)
                    response.raise_for_status()
                    root = ElementTree.fromstring(self._content(response))
                except (httpx.HTTPError, ElementTree.ParseError, OSError):
                    continue

                root_name = self._local_name(root.tag)
                if root_name == "sitemapindex":
                    pending.extend(
                        urljoin(str(response.url), loc)
                        for loc in self._locs(root, "sitemap")
                    )
                    continue
                if root_name == "urlset":
                    discovered.extend(self._locs(root, "url"))

        return list(dict.fromkeys(discovered))

    async def _sitemap_urls_from_robots(self, origin: str) -> list[str]:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                response = await client.get(urljoin(origin, "/robots.txt"))
                if response.is_success:
                    return [
                        line.split(":", 1)[1].strip()
                        for line in response.text.splitlines()
                        if line.lower().startswith("sitemap:")
                        and line.split(":", 1)[1].strip()
                    ]
        except httpx.HTTPError:
            pass
        return []

    @staticmethod
    def _origin(base_url: str) -> str:
        parsed = urlparse(base_url)
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}"
        return f"https://{parsed.path.rstrip('/')}"

    @staticmethod
    def _content(response: httpx.Response) -> bytes:
        content = response.content
        if response.url.path.endswith(".gz"):
            try:
                return gzip.decompress(content)
            except gzip.BadGzipFile:
                pass
        return content

    @classmethod
    def _locs(cls, root: ElementTree.Element, parent_name: str) -> list[str]:
        return [
            loc.text.strip()
            for parent in root.iter()
            if cls._local_name(parent.tag) == parent_name
            for loc in parent
            if cls._local_name(loc.tag) == "loc" and loc.text and loc.text.strip()
        ]

    @staticmethod
    def _local_name(tag: str) -> str:
        return tag.rsplit("}", 1)[-1]


class DomainMapperAdapter:
    """Adapter que isola a dependência concreta do crawl4ai.DomainMapper."""

    async def scan(self, url: str, **kwargs: Any) -> list[dict[str, Any]]:
        from crawl4ai import DomainMapper

        async with DomainMapper() as mapper:
            return await mapper.scan(url, **kwargs)


class PlaywrightDiscovererProtocol(Protocol):
    async def discover(
        self,
        base_url: str,
        policy: dict[str, Any] | None = None,
    ) -> list[str]: ...


class URLDiscoverer:
    """Descobre URLs a partir de uma URL base."""

    def __init__(
        self,
        mapper: URLMapper | None = None,
        max_urls: int = 500,
        listing_patterns: list[str] | None = None,
        sitemap_fetcher: SitemapFetcher | None = None,
        mapper_timeout_seconds: float = 60.0,
        playwright_discoverer: PlaywrightDiscovererProtocol | None = None,
        default_strategies: list[str] | None = None,
        max_pages: int = 100,
    ):
        self._mapper = mapper or DomainMapperAdapter()
        self._sitemap_fetcher = sitemap_fetcher or HttpSitemapFetcher()
        self._mapper_timeout_seconds = mapper_timeout_seconds
        self.max_urls = max_urls
        self._listing_patterns = (
            _DEFAULT_LISTING_PATTERNS
            if listing_patterns is None
            else listing_patterns
        )
        self._default_strategies = list(default_strategies) if default_strategies else []
        self._playwright_discoverer = (
            playwright_discoverer
            or PlaywrightListingDiscoverer(
                max_urls=max_urls,
                max_pages=max_pages,
                listing_patterns=listing_patterns,
            )
        )

    async def discover(self, base_url: str, policy: dict[str, Any] | None = None) -> list[str]:
        """Descobre URLs a partir da URL base."""
        policy = policy or {}
        configuration = policy.get("configuration")
        options = dict(configuration) if isinstance(configuration, dict) else {}
        options.update({
            key: policy[key]
            for key in ["max_urls", "include_subdomains", "use_browser_for_homepage", "query", "score_threshold", "probe_paths", "common_subdomains"]
            if key in policy
        })
        selected_sources = self._selected_sources(policy)
        mapper_sources = [
            source
            for source in selected_sources
            if source.lower() not in _PLAYWRIGHT_STRATEGIES
        ]
        results: list[dict[str, Any]] = []

        if self._should_run_domain_mapper(selected_sources, mapper_sources):
            valid_mapper_sources = [
                s for s in mapper_sources if s.lower() in _DOMAIN_MAPPER_SOURCES
            ]
            source_arg = valid_mapper_sources or mapper_sources
            mapper_policy = {
                **({"source": "+".join(source_arg)} if source_arg else {}),
                **options,
            }
            try:
                mapped = await asyncio.wait_for(
                    self._mapper.scan(base_url, **mapper_policy),
                    timeout=self._mapper_timeout_seconds,
                )
                results = list(mapped)
            except (TimeoutError, asyncio.TimeoutError):
                logger.warning(
                    "crawler_domain_mapper_timed_out base_url=%s timeout_seconds=%s",
                    base_url,
                    self._mapper_timeout_seconds,
                )
                results = []

        if self._uses_sitemap(selected_sources):
            logger.info("crawler_sitemap_source_started base_url=%s", base_url)
            fallback_urls = await self._sitemap_fetcher.fetch(base_url)
            results.extend(
                {"url": url}
                for url in fallback_urls
            )
            logger.info(
                "crawler_sitemap_source_finished base_url=%s urls=%s",
                base_url,
                len(fallback_urls),
            )

        if self._uses_playwright(selected_sources):
            logger.info("crawler_playwright_source_started base_url=%s", base_url)
            playwright_urls = await self._playwright_discoverer.discover(
                base_url,
                policy,
            )
            results.extend({"url": url, "trusted": True} for url in playwright_urls)
            logger.info(
                "crawler_playwright_source_finished base_url=%s urls=%s",
                base_url,
                len(playwright_urls),
            )

        return self._listing_urls(
            results,
            int(options.get("max_urls", self.max_urls)),
        )

    def _listing_urls(self, results: list[dict[str, Any]], max_urls: int) -> list[str]:
        urls: list[str] = []
        seen: set[str] = set()
        compiled = [re.compile(pattern) for pattern in self._listing_patterns]
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            if (
                not item.get("trusted")
                and compiled
                and not any(pattern.search(url) for pattern in compiled)
            ):
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= max_urls:
                break

        return urls

    def _selected_sources(self, policy: dict[str, Any]) -> list[str]:
        raw = policy.get("sources")
        if not isinstance(raw, list):
            raw = policy.get("strategies")
        if not isinstance(raw, list):
            return list(self._default_strategies)
        return [str(item) for item in raw if item]

    @staticmethod
    def _should_run_domain_mapper(
        selected_sources: list[str],
        mapper_sources: list[str],
    ) -> bool:
        if not selected_sources:
            return True
        return bool(mapper_sources)

    @staticmethod
    def _uses_sitemap(selected_sources: list[str]) -> bool:
        return not selected_sources or any(
            s.lower() == "sitemap" for s in selected_sources
        )

    @staticmethod
    def _uses_playwright(selected_sources: list[str]) -> bool:
        return any(s.lower() in _PLAYWRIGHT_STRATEGIES for s in selected_sources)

    def discover_sync(self, base_url: str, policy: dict[str, Any] | None = None) -> list[str]:
        """Versão síncrona de ``discover``."""
        return asyncio.run(self.discover(base_url, policy))
