from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from crawler_machine.config import CrawlerConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.crawl4ai_llm_client import Crawl4AILlmClient

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
        self._crawl_and_extract = (
            crawl_and_extract or Crawl4AILlmClient(llm_config, config).extract
        )

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
