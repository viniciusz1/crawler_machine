from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.crawl4ai_browser import Crawl4AIBrowser

logger = logging.getLogger(__name__)

FetchFunc = Callable[[str], Awaitable[CrawlResult]]


class HttpRunner:
    """Faz requisições HTTP usando Crawl4AI e retorna CrawlResult com HTML."""

    def __init__(
        self,
        config: CrawlerConfig,
        fetch: FetchFunc | None = None,
    ):
        self._config = config
        self._fetch = fetch or Crawl4AIBrowser(config).fetch

    async def run(self, url: str) -> CrawlResult:
        """Executa fetch com retry em erros transientes."""
        pending = url
        last_error: str | None = None

        for attempt in range(self._config.retry_attempts):
            result = await self._fetch(pending)
            if result.success or not self._is_transient_error(result.error):
                return result
            last_error = result.error
            if attempt < self._config.retry_attempts - 1:
                delay = self._config.retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        return CrawlResult(
            url=url,
            success=False,
            data=[],
            error=last_error or "Max retry attempts exceeded",
        )

    @staticmethod
    def _is_transient_error(error_message: str | None) -> bool:
        """Verifica se o erro parece transitório."""
        if not error_message:
            return False
        lowered = error_message.lower()
        return any(
            keyword in lowered
            for keyword in ("timeout", "timed out", "navigation", "navigating", "net::")
        )
