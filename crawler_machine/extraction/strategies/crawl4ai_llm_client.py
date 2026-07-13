from __future__ import annotations

import json
import logging
import os
from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from crawler_machine.config import CrawlerConfig, LLMConfig
from crawler_machine.extraction.strategies._constants import _DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)


class Crawl4AILlmClient:
    """Adapter que isola a chamada ao LLM do Crawl4AI."""

    def __init__(
        self,
        llm_config: LLMConfig,
        crawler_config: CrawlerConfig | None = None,
    ):
        self._llm_config = llm_config
        self._crawler_config = crawler_config

    async def extract(
        self,
        url: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Executa extração por LLM sobre o HTML completo da URL."""
        api_key = os.environ.get(self._llm_config.api_key_env, "")
        extraction_strategy = LLMExtractionStrategy(
            provider=self._llm_config.provider,
            api_token=api_key,
            base_url=self._llm_config.base_url,
            instruction=instruction,
            schema=schema,
            extraction_type="schema",
        )

        browser_config = BrowserConfig(
            headless=self._crawler_config.headless if self._crawler_config else True,
            viewport_width=1366,
            viewport_height=768,
            user_agent=(
                self._crawler_config.user_agent
                if self._crawler_config and self._crawler_config.user_agent
                else _DEFAULT_USER_AGENT
            ),
            enable_stealth=(
                self._crawler_config.enable_stealth
                if self._crawler_config
                else True
            ),
        )
        crawler_config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            wait_for="css:body",
            wait_until=(
                self._crawler_config.wait_until
                if self._crawler_config
                else "domcontentloaded"
            ),
            page_timeout=(
                self._crawler_config.page_timeout
                if self._crawler_config
                else 30000
            ),
            remove_overlay_elements=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=crawler_config)

        if not result.success:
            raise RuntimeError(result.error_message or "LLM extraction failed")

        content = result.extracted_content
        if isinstance(content, str):
            return json.loads(content)
        return dict(content)
