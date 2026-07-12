from __future__ import annotations

import asyncio
import re
from typing import Any, Protocol

from crawl4ai import DomainMapper

_DEFAULT_LISTING_PATTERNS = [
    r"/imovel/",
    r"/(comprar|alugar|vender)/",
    r"/(apartamento|casa|terreno|sobrado|sala-comercial|loft|chacara|rural)-",
]


class URLMapper(Protocol):
    """Porta para descoberta de URLs."""

    async def scan(self, url: str) -> list[dict[str, Any]]: ...


class URLDiscoverer:
    """Descobre URLs a partir de uma URL base."""

    def __init__(
        self,
        mapper: URLMapper | None = None,
        max_urls: int = 500,
        listing_patterns: list[str] | None = None,
    ):
        self._mapper = mapper
        self.max_urls = max_urls
        self._listing_patterns = (
            _DEFAULT_LISTING_PATTERNS
            if listing_patterns is None
            else listing_patterns
        )

    async def discover(self, base_url: str) -> list[str]:
        """Descobre URLs a partir da URL base."""
        mapper = self._mapper
        if mapper is None:
            async with DomainMapper() as domain_mapper:
                results = await domain_mapper.scan(base_url)
        else:
            results = await mapper.scan(base_url)

        urls: list[str] = []
        compiled = [re.compile(pattern) for pattern in self._listing_patterns]
        for item in results:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            if not isinstance(url, str) or not url:
                continue
            if compiled and not any(pattern.search(url) for pattern in compiled):
                continue
            urls.append(url)
            if len(urls) >= self.max_urls:
                break

        return urls

    def discover_sync(self, base_url: str) -> list[str]:
        """Versão síncrona de ``discover``."""
        return asyncio.run(self.discover(base_url))
