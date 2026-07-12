from __future__ import annotations

import json
import logging
import os
from typing import Any, Awaitable, Callable

import litellm
from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult

logger = logging.getLogger(__name__)

ExtractMissingFunc = Callable[[str, str, set[str]], Awaitable[dict[str, Any]]]


class FitMarkdownLlmStrategy:
    """Usa mini-LLM sobre o markdown filtrado para campos semânticos faltantes."""

    name = "fit_markdown_llm"
    enabled = False

    def __init__(
        self,
        fields: list[FieldConfig],
        llm_config: LLMConfig,
        markdown_generator: DefaultMarkdownGenerator | None = None,
        extract_missing: ExtractMissingFunc | None = None,
    ):
        self._fields = {field.name: field for field in fields}
        self._llm_config = llm_config
        self._markdown_generator = markdown_generator or self._default_generator()
        self._extract_missing = extract_missing or self._default_extract_missing

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        if previous is None or not previous.html:
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error="Fit markdown LLM requires HTML from previous extraction",
            )

        try:
            md_result = self._markdown_generator.generate_markdown(
                input_html=previous.html,
                base_url=url,
            )
            markdown = md_result.fit_markdown or md_result.raw_markdown
        except Exception as exc:
            logger.exception("Markdown generation failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"Markdown generation failed: {exc}",
            )

        try:
            data = await self._extract_missing(url, markdown, set(self._fields.keys()))
        except Exception as exc:
            logger.exception("LLM extraction failed for %s", url)
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error=f"LLM extraction failed: {exc}",
            )

        record = {k: v for k, v in data.items() if k in self._fields and v is not None}
        return CrawlResult(
            url=url,
            success=True,
            data=[record] if record else [],
            html=previous.html,
            images=previous.images,
        )

    async def _default_extract_missing(
        self, url: str, markdown: str, missing: set[str]
    ) -> dict[str, Any]:
        """Chama LLM para extrair campos faltantes do markdown."""
        api_key = os.environ.get(self._llm_config.api_key_env, "")
        field_list = ", ".join(missing)
        prompt = (
            "Você é um extrator de dados de imóveis. "
            "Analise o markdown abaixo e extraia os seguintes campos, "
            "retornando apenas um objeto JSON válido:\n\n"
            f"Campos: {field_list}\n\n"
            "Markdown:\n"
            f"{markdown}\n\n"
            "Responda apenas com JSON."
        )

        response = await litellm.acompletion(
            model=self._llm_config.provider,
            api_key=api_key,
            api_base=self._llm_config.base_url,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=1000,
        )

        content = response["choices"][0]["message"]["content"]
        cleaned = self._extract_json(content)
        return json.loads(cleaned)

    @staticmethod
    def _extract_json(text: str) -> str:
        """Extrai bloco JSON de uma resposta LLM."""
        text = text.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()
        return text

    @staticmethod
    def _default_generator() -> DefaultMarkdownGenerator:
        filter_strategy = PruningContentFilter(
            threshold=0.4,
            threshold_type="fixed",
        )
        return DefaultMarkdownGenerator(content_filter=filter_strategy)
