from __future__ import annotations

from typing import Any

from crawler_machine.config import DomainConfig
from crawler_machine.extraction.engine import REQUIRED_FIELDS, CrawlEngine
from crawler_machine.extraction.strategies import (
    CssStrategy,
    FitMarkdownLlmStrategy,
    FitMarkdownRegexStrategy,
    LlmFullHtmlStrategy,
    XPathStrategy,
)


def build_crawl_engine(
    config: DomainConfig,
    schema: dict[str, Any],
    enable_llm_fallback: bool | None = None,
) -> CrawlEngine:
    """Monta a CrawlEngine com a cadeia de fallback habilitada."""
    schemas = schema.get("schemas", {})
    xpath_schema = schemas.get("xpath", schema)
    css_schema = schemas.get("css", schema)

    llm_enabled = (
        enable_llm_fallback
        if enable_llm_fallback is not None
        else config.crawler.enable_llm_fallback
    )
    fit_markdown_llm_enabled = config.crawler.enable_fit_markdown_llm

    strategies = [XPathStrategy(config=config.crawler, schema=xpath_schema)]

    if css_schema:
        css = CssStrategy(schema=css_schema)
        strategies.append(css)

    if config.crawler.enable_fit_markdown_regex:
        strategies.append(FitMarkdownRegexStrategy(fields=config.fields))

    if fit_markdown_llm_enabled:
        fit_llm = FitMarkdownLlmStrategy(
            fields=config.fields,
            llm_config=config.llm,
        )
        fit_llm.enabled = True
        strategies.append(fit_llm)

    if llm_enabled:
        full_llm = LlmFullHtmlStrategy(
            config=config.crawler,
            fields=config.fields,
            llm_config=config.llm,
        )
        full_llm.enabled = True
        strategies.append(full_llm)

    return CrawlEngine(
        config=config.crawler,
        required_fields=REQUIRED_FIELDS,
        strategies=strategies,
    )
