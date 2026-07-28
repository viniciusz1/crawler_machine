from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from crawler_machine.config import CrawlerConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.crawl4ai_llm_client import Crawl4AILlmClient

logger = logging.getLogger(__name__)

CrawlAndExtractFunc = Callable[
    [str, str, str, dict[str, Any]], Awaitable[dict[str, Any]]
]


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
        self._fields = fields
        self._llm_config = llm_config
        self._crawl_and_extract = (
            crawl_and_extract or Crawl4AILlmClient(llm_config).extract
        )

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        """Extrai campos faltantes usando LLM sobre o HTML completo."""
        if previous is None or not previous.html:
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error="LLM full HTML requires previously collected HTML",
            )

        present = {
            key
            for item in previous.data
            for key, value in item.items()
            if self._is_meaningful(value)
        }
        missing = {field.name for field in self._fields}.difference(present)
        if not missing:
            return CrawlResult(
                url=url,
                success=True,
                data=[],
                html=previous.html,
                images=previous.images,
            )

        schema = self._build_json_schema(missing)
        instruction = self._build_instruction(missing)

        try:
            data = await self._crawl_and_extract(
                url,
                previous.html,
                instruction,
                schema,
            )
        except Exception as exc:
            logger.exception("LLM full HTML extraction failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"LLM full HTML extraction failed: {exc}",
            )

        record = {k: v for k, v in data.items() if k in missing and v is not None}
        return CrawlResult(
            url=url,
            success=True,
            data=[record] if record else [],
            html=previous.html if previous else None,
            images=previous.images if previous else [],
        )

    def _build_json_schema(self, missing: set[str]) -> dict[str, Any]:
        """Monta JSON schema para a estratégia nativa do Crawl4AI."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in self._fields:
            if field.name not in missing:
                continue
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

    def _build_instruction(self, missing: set[str]) -> str:
        """Monta instrução natural para o LLM."""
        field_descriptions = [
            f"{field.name}: {field.description}"
            for field in self._fields
            if field.name in missing
        ]
        return (
            "Extraia as seguintes informações do imóvel descrito na página. "
            "Retorne apenas um objeto JSON válido.\n\n"
            + "\n".join(field_descriptions)
        )

    @staticmethod
    def _is_meaningful(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, dict)):
            return bool(value)
        return True
