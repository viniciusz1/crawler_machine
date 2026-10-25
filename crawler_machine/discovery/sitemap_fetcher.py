from __future__ import annotations

import gzip
from typing import Protocol
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree

import httpx


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
