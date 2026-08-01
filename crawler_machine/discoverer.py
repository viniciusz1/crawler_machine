from __future__ import annotations

import asyncio
import gzip
import logging
import re
from typing import Any, Protocol
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

_DEFAULT_LISTING_PATTERNS = [
    r"/imovel/",
    r"/\d{3,}/?(?:\?.*)?$",
    r"/detalhes_(?:loc|vd)\.php\?imovel=\d+",
    r"/(comprar|alugar|vender)/",
    r"/(apartamento|casa|terreno|sobrado|sala-comercial|loft|chacara|rural)-",
]


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


class URLDiscoverer:
    """Descobre URLs a partir de uma URL base."""

    def __init__(
        self,
        mapper: URLMapper | None = None,
        max_urls: int = 500,
        listing_patterns: list[str] | None = None,
        sitemap_fetcher: SitemapFetcher | None = None,
        mapper_timeout_seconds: float = 60.0,
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
        mapper_policy = {
            **({"source": "+".join(policy["sources"])} if policy.get("sources") else {}),
            **options,
        }
        try:
            mapped = await asyncio.wait_for(
                self._mapper.scan(base_url, **mapper_policy),
                timeout=self._mapper_timeout_seconds,
            )
            results = list(mapped)
        except TimeoutError:
            logger.warning(
                "crawler_domain_mapper_timed_out base_url=%s timeout_seconds=%s",
                base_url,
                self._mapper_timeout_seconds,
            )
            results = []
        if self._uses_sitemap(policy):
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
            if compiled and not any(pattern.search(url) for pattern in compiled):
                continue
            if url in seen:
                continue
            seen.add(url)
            urls.append(url)
            if len(urls) >= max_urls:
                break

        return urls

    @staticmethod
    def _uses_sitemap(policy: dict[str, Any]) -> bool:
        sources = policy.get("sources")
        return not isinstance(sources, list) or "sitemap" in sources

    def discover_sync(self, base_url: str, policy: dict[str, Any] | None = None) -> list[str]:
        """Versão síncrona de ``discover``."""
        return asyncio.run(self.discover(base_url, policy))
