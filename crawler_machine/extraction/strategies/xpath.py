from __future__ import annotations

import logging
from typing import Any

from crawl4ai.extraction_strategy import JsonXPathExtractionStrategy

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.http_runner import HttpRunner

logger = logging.getLogger(__name__)


class XPathStrategy:
    """Estratégia de extração usando schema XPath gerado por IA."""

    name = "xpath"
    enabled = True

    def __init__(
        self,
        config: CrawlerConfig,
        schema: dict[str, Any],
        http_runner: HttpRunner | None = None,
    ):
        self._config = config
        self._schema = schema
        self._http_runner = http_runner or HttpRunner(config)

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        """Extrai dados usando XPath, buscando HTML se necessário."""
        if previous is not None and previous.html:
            html = previous.html
            images = previous.images
        else:
            fetched = await self._http_runner.run(url)
            if not fetched.success:
                return fetched
            html = fetched.html
            images = fetched.images

        if not html:
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error="No HTML available for XPath extraction",
            )

        try:
            strategy = JsonXPathExtractionStrategy(schema=self._schema)
            data = strategy.extract(url, html)
        except Exception as exc:
            logger.exception("XPath extraction failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"XPath extraction failed: {exc}",
            )

        return CrawlResult(
            url=url,
            success=True,
            data=data,
            html=html,
            images=images,
        )
