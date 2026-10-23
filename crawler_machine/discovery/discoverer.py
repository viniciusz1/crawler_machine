from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Protocol

from crawler_machine.discovery.items_catalog import (
    DEFAULT_PROPERTY_PATTERNS,
    PlaywrightListingDiscoverer,
)
from crawler_machine.discovery.sitemap_fetcher import (
    HttpSitemapFetcher,
    SitemapFetcher,
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

_DEFAULT_LISTING_PATTERNS = list(DEFAULT_PROPERTY_PATTERNS)


class URLMapper(Protocol):
    """Porta para descoberta de URLs."""

    async def scan(self, url: str, **kwargs: Any) -> list[dict[str, Any]]: ...


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
            for key in [
                "max_urls",
                "include_subdomains",
                "use_browser_for_homepage",
                "query",
                "score_threshold",
                "probe_paths",
                "common_subdomains",
            ]
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
