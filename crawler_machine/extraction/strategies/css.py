from __future__ import annotations

import logging
from typing import Any

from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

from crawler_machine.extraction.result import CrawlResult

logger = logging.getLogger(__name__)


class CssStrategy:
    """Estratégia de extração usando schema CSS sobre HTML já obtido."""

    name = "css"
    enabled = True

    def __init__(self, schema: dict[str, Any]):
        self._schema = schema

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        """Extrai dados usando CSS sobre o HTML acumulado."""
        if previous is None or not previous.html:
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error="CSS strategy requires HTML from previous extraction",
            )

        try:
            strategy = JsonCssExtractionStrategy(schema=self._schema)
            data = strategy.extract(url, previous.html)
        except Exception as exc:
            logger.exception("CSS extraction failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"CSS extraction failed: {exc}",
            )

        return CrawlResult(
            url=url,
            success=True,
            data=data,
            html=previous.html,
            images=previous.images,
        )
