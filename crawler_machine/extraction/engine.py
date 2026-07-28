from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

from crawler_machine.config import REQUIRED_FIELDS, CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategy import ExtractionStrategy
from crawler_machine.extraction.strategies.http_runner import HttpRunner

logger = logging.getLogger(__name__)


class HtmlCollector(Protocol):
    async def run(self, url: str) -> CrawlResult: ...


class CrawlEngine:
    """Orquestra a cadeia de fallback de extração sobre uma lista de URLs."""

    def __init__(
        self,
        config: CrawlerConfig,
        required_fields: set[str] | tuple[str, ...],
        strategies: list[ExtractionStrategy],
        html_collector: HtmlCollector | None = None,
    ):
        self._config = config
        self._required_fields = set(required_fields)
        self._strategies = [s for s in strategies if s.enabled]
        self._html_collector = html_collector or HttpRunner(config)

    async def crawl(
        self,
        urls: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa a cadeia de fallback para cada URL."""
        data: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for index, chunk in enumerate(self._chunks(urls, self._config.chunk_size)):
            if index > 0 and self._config.chunk_delay > 0:
                await asyncio.sleep(self._config.chunk_delay)

            chunk_results = await asyncio.gather(
                *[self._crawl_single(url) for url in chunk]
            )

            for result, error in chunk_results:
                if error is not None:
                    errors.append(error)
                if result is not None:
                    data.append(result)

        return data, errors

    def crawl_sync(
        self, urls: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Versão síncrona de ``crawl``."""
        return asyncio.run(self.crawl(urls))

    async def _crawl_single(
        self, url: str
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        """Executa a cadeia de fallback para uma única URL."""
        try:
            fetched = await self._html_collector.run(url)
        except Exception as exc:  # pragma: no cover - adapter safety net
            logger.exception("HTML collection failed for %s", url)
            return None, {"url": url, "error": str(exc)}
        if not fetched.success:
            return None, {
                "url": url,
                "error": fetched.error or "HTML collection failed",
            }
        if not fetched.html:
            return None, {"url": url, "error": "HTML collection returned no HTML"}

        accumulated: dict[str, Any] = {}
        trace: dict[str, str] = {}
        last_error: str | None = None

        if "url" in self._required_fields:
            accumulated["url"] = url
            trace["url"] = "url"

        for strategy in self._strategies:
            previous = CrawlResult(
                url=fetched.url,
                success=True,
                data=[dict(accumulated)] if accumulated else [],
                html=fetched.html,
                images=fetched.images,
            )
            try:
                result = await strategy.extract(url, previous)
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("Strategy %s failed for %s", strategy.name, url)
                last_error = str(exc)
                continue

            if not result.success:
                last_error = result.error or f"{strategy.name} failed"
                continue

            for record in result.data:
                if isinstance(record, dict):
                    for key, value in record.items():
                        if key not in accumulated and self._is_meaningful(value):
                            accumulated[key] = value
                            trace[key] = strategy.name

            present_fields = {
                key
                for key, value in accumulated.items()
                if self._is_meaningful(value)
            }
            if self._required_fields.issubset(present_fields):
                break

        if not accumulated or (set(accumulated.keys()) == {"url"} and last_error is not None):
            return None, {"url": url, "error": last_error or "no data extracted"}

        accumulated["_extraction_trace"] = trace
        return accumulated, None

    @staticmethod
    def _is_meaningful(value: Any) -> bool:
        """Verifica se um valor extraído deve ser considerado presente."""
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if isinstance(value, (list, dict)) and not value:
            return False
        return True

    @staticmethod
    def _chunks(items: list[str], size: int) -> list[list[str]]:
        """Divide uma lista em lotes de tamanho máximo ``size``."""
        if size <= 0:
            return [items]
        return [items[i : i + size] for i in range(0, len(items), size)]
