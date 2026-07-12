from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable

from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, LLMConfig as Crawl4AILLMConfig
from crawl4ai.extraction_strategy import LLMExtractionStrategy

from crawler_machine.config import CrawlerConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies._constants import _DEFAULT_USER_AGENT

logger = logging.getLogger(__name__)

CrawlAndExtractFunc = Callable[[str, str, dict[str, Any]], Awaitable[dict[str, Any]]]


class LlmFullHtmlStrategy:
    """Estratégia de último recurso usando LLM nativo do Crawl4AI sobre o HTML."""

    name = "llm_full_html"
    enabled = False

    def __init__(
        self,
        config: CrawlerConfig | None,
        fields: list[FieldConfig],
        llm_config: LLMConfig,
        crawl_and_extract: CrawlAndExtractFunc | None = None,
    ):
        self._config = config
        self._fields = fields
        self._llm_config = llm_config
        self._crawl_and_extract = crawl_and_extract or self._default_crawl_and_extract

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        """Extrai campos faltantes usando LLM sobre o HTML completo."""
        schema = self._build_json_schema()
        instruction = self._build_instruction()

        try:
            data = await self._crawl_and_extract(url, instruction, schema)
        except Exception as exc:
            logger.exception("LLM full HTML extraction failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"LLM full HTML extraction failed: {exc}",
            )

        record = {k: v for k, v in data.items() if v is not None}
        return CrawlResult(
            url=url,
            success=True,
            data=[record] if record else [],
            html=previous.html if previous else None,
            images=previous.images if previous else [],
        )

    def _build_json_schema(self) -> dict[str, Any]:
        """Monta JSON schema para a estratégia nativa do Crawl4AI."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in self._fields:
            json_type = "string"
            if field.coerce in ("int", "currency"):
                json_type = "number"
            properties[field.name] = {
                "type": [json_type, "null"],
                "description": field.description,
            }
            required.append(field.name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _build_instruction(self) -> str:
        """Monta instrução natural para o LLM."""
        field_descriptions = [
            f"{field.name}: {field.description}" for field in self._fields
        ]
        return (
            "Extraia as seguintes informações do imóvel descrito na página. "
            "Retorne apenas um objeto JSON válido.\n\n"
            + "\n".join(field_descriptions)
        )

    async def _default_crawl_and_extract(
        self, url: str, instruction: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """Execução real usando Crawl4AI + LLMExtractionStrategy."""
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
            headless=self._config.headless if self._config else True,
            viewport_width=1366,
            viewport_height=768,
            user_agent=(
                self._config.user_agent if self._config and self._config.user_agent else _DEFAULT_USER_AGENT
            ),
            enable_stealth=self._config.enable_stealth if self._config else True,
        )
        crawler_config = CrawlerRunConfig(
            extraction_strategy=extraction_strategy,
            wait_for="css:body",
            wait_until=self._config.wait_until if self._config else "domcontentloaded",
            page_timeout=self._config.page_timeout if self._config else 30000,
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
