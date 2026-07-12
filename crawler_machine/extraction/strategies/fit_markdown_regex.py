from __future__ import annotations

import logging
import re
from typing import Any

from crawl4ai.content_filter_strategy import PruningContentFilter
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator

from crawler_machine.config import FieldConfig
from crawler_machine.extraction.result import CrawlResult

logger = logging.getLogger(__name__)

_DEFAULT_PATTERNS: dict[str, list[str]] = {
    "valor": [
        r"R\$\s*[\d.]+(?:,\d{2})?",
        r"RS\s*[\d.]+(?:,\d{2})?",
    ],
    "area": [
        r"(\d+(?:[.,]\d+)?)\s*m[²2]",
        r"(\d+(?:[.,]\d+)?)\s*metros",
    ],
    "quartos": [
        r"(\d+)\s*(?:quarto|dormitório|dorm|suite|suíte|qtos?|dts?)",
    ],
    "banheiros": [
        r"(\d+)\s*(?:banheiro|wc|toilet)",
    ],
    "vagas": [
        r"(\d+)\s*(?:vaga|garagem)",
    ],
}


class FitMarkdownRegexStrategy:
    """Extrai campos numéricos/monéticos do markdown filtrado via regex."""

    name = "fit_markdown_regex"
    enabled = True

    def __init__(
        self,
        fields: list[FieldConfig],
        markdown_generator: DefaultMarkdownGenerator | None = None,
        patterns: dict[str, list[str]] | None = None,
    ):
        self._fields = {field.name: field for field in fields}
        self._markdown_generator = markdown_generator or self._default_generator()
        self._patterns = patterns or _DEFAULT_PATTERNS

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        if previous is None or not previous.html:
            return CrawlResult(
                url=url,
                success=False,
                data=[],
                error="Fit markdown regex requires HTML from previous extraction",
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

        record: dict[str, Any] = {}
        for field_name, field in self._fields.items():
            if field_name in self._patterns:
                value = self._extract_first(markdown, self._patterns[field_name])
                if value is not None:
                    record[field_name] = value

        image = self._extract_first_image(previous.html)
        if image and "imagem" in self._fields:
            record["imagem"] = image

        return CrawlResult(
            url=url,
            success=True,
            data=[record] if record else [],
            html=previous.html,
            images=previous.images,
        )

    @staticmethod
    def _extract_first(text: str, patterns: list[str]) -> Any:
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                value = match.group(1) if match.groups() else match.group(0)
                if value:
                    return FitMarkdownRegexStrategy._normalize_numeric(value)
        return None

    @staticmethod
    def _normalize_numeric(value: str) -> Any:
        """Tenta converter valores numéricos; mantém string caso contrário."""
        cleaned = value.strip().lower().replace("r$", "").replace(" ", "")
        try:
            if "," in cleaned and "." in cleaned:
                # 450.000,00 -> 450000.00
                cleaned = cleaned.replace(".", "").replace(",", ".")
            elif "," in cleaned:
                # 120,5 -> 120.5 (decimal) ou 1.200,00 -> 1200.00
                parts = cleaned.split(",")
                if len(parts[-1]) == 2:
                    cleaned = cleaned.replace(".", "").replace(",", ".")
                else:
                    cleaned = cleaned.replace(",", ".")
            return float(cleaned)
        except ValueError:
            return value.strip()

    @staticmethod
    def _extract_first_image(html: str) -> str | None:
        """Extrai a primeira URL de imagem do HTML."""
        match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def _default_generator() -> DefaultMarkdownGenerator:
        filter_strategy = PruningContentFilter(
            threshold=0.4,
            threshold_type="fixed",
        )
        return DefaultMarkdownGenerator(content_filter=filter_strategy)
