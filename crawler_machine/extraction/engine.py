from __future__ import annotations

import asyncio
import logging
from typing import Any

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategy import ExtractionStrategy

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = {"bairro", "cidade", "valor", "tipo_imovel", "url", "imagem"}


class CrawlEngine:
    """Orquestra a cadeia de fallback de extração sobre uma lista de URLs."""

    def __init__(
        self,
        config: CrawlerConfig,
        required_fields: set[str],
        strategies: list[ExtractionStrategy],
    ):
        self._config = config
        self._required_fields = required_fields
        self._strategies = [s for s in strategies if s.enabled]

    async def crawl(self, urls: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa a cadeia de fallback para cada URL."""
        data: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for index, chunk in enumerate(self._chunks(urls, self._config.chunk_size)):
            if index > 0 and self._config.chunk_delay > 0:
                await asyncio.sleep(self._config.chunk_delay)

            chunk_results = await asyncio.gather(*[
                self._crawl_single(url) for url in chunk
            ])

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
        previous: CrawlResult | None = None
        accumulated: dict[str, Any] = {}
        trace: dict[str, str] = {}
        last_error: str | None = None

        if "url" in self._required_fields:
            accumulated["url"] = url
            trace["url"] = "url"

        for strategy in self._strategies:
            try:
                result = await strategy.extract(url, previous)
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("Strategy %s failed for %s", strategy.name, url)
                last_error = str(exc)
                continue

            if not result.success:
                last_error = result.error or f"{strategy.name} failed"
                continue

            if previous is None:
                previous = result
            elif result.html and not previous.html:
                previous = CrawlResult(
                    url=previous.url,
                    success=previous.success,
                    data=previous.data,
                    error=previous.error,
                    images=previous.images,
                    html=result.html,
                )

            for record in result.data:
                if isinstance(record, dict):
                    for key, value in record.items():
                        if key not in accumulated and self._is_meaningful(value):
                            accumulated[key] = value
                            trace[key] = strategy.name

            if self._required_fields.issubset({
                k for k, v in accumulated.items() if self._is_meaningful(v)
            }):
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
        return True

    @staticmethod
    def _chunks(items: list[str], size: int) -> list[list[str]]:
        """Divide uma lista em lotes de tamanho máximo ``size``."""
        if size <= 0:
            return [items]
        return [items[i : i + size] for i in range(0, len(items), size)]
