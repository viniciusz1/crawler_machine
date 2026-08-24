from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.crawl4ai_browser import Crawl4AIBrowser

logger = logging.getLogger(__name__)

FetchFunc = Callable[[str], Awaitable[CrawlResult]]
FetchManyFunc = Callable[[list[str]], Awaitable[list[CrawlResult]]]


class HttpRunner:
    """Faz requisições HTTP usando Crawl4AI e retorna CrawlResult com HTML."""

    def __init__(
        self,
        config: CrawlerConfig,
        fetch: FetchFunc | None = None,
        fetch_many: FetchManyFunc | None = None,
    ):
        self._config = config
        if fetch_many is not None:
            self._fetch_many = fetch_many
        elif fetch is not None:

            async def fetch_individually(urls: list[str]) -> list[CrawlResult]:
                return list(await asyncio.gather(*(fetch(url) for url in urls)))

            self._fetch_many = fetch_individually
        else:
            self._fetch_many = Crawl4AIBrowser(config).fetch_many

    async def run(self, url: str) -> CrawlResult:
        """Executa uma coleta unitária sobre o fluxo em lote."""
        return (await self.run_many([url]))[0]

    async def run_many(self, urls: list[str]) -> list[CrawlResult]:
        """Executa fetch em lote e repete somente falhas transientes."""
        if not urls:
            return []

        pending = list(dict.fromkeys(urls))
        completed: dict[str, CrawlResult] = {}

        for attempt in range(self._config.retry_attempts):
            batch_results = await self._fetch_many(pending)
            if len(batch_results) != len(pending):
                raise RuntimeError(
                    "Batch HTML collection returned a different number of results"
                )

            retry_urls: list[str] = []
            for requested_url, result in zip(pending, batch_results, strict=True):
                should_retry = (
                    not result.success
                    and self._is_transient_error(result.error)
                    and attempt < self._config.retry_attempts - 1
                )
                if should_retry:
                    retry_urls.append(requested_url)
                else:
                    completed[requested_url] = result

            pending = retry_urls
            if not pending:
                break
            if attempt < self._config.retry_attempts - 1:
                delay = self._config.retry_base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        for url in pending:
            completed[url] = CrawlResult(
                url=url,
                success=False,
                data=[],
                error="Max retry attempts exceeded",
            )

        return [
            completed.get(
                url,
                CrawlResult(
                    url=url,
                    success=False,
                    data=[],
                    error="Max retry attempts exceeded",
                ),
            )
            for url in urls
        ]

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
