from __future__ import annotations

import logging
from typing import Any

from crawler_machine.config import DomainConfig
from crawler_machine.extraction.engine import REQUIRED_FIELDS, CrawlEngine, HtmlCollector
from crawler_machine.extraction.strategies import (
    CssStrategy,
    FitMarkdownLlmStrategy,
    FitMarkdownRegexStrategy,
    LlmFullHtmlStrategy,
    XPathStrategy,
)
from crawler_machine.pipeline_helpers import detect_schema_type

CANONICAL_EXTRACTION_STRATEGIES = (
    "xpath",
    "css",
    "fit_markdown_regex",
    "fit_markdown_llm",
    "llm_full_html",
)

logger = logging.getLogger(__name__)


def build_crawl_engine(
    config: DomainConfig,
    schema: dict[str, Any],
    enable_llm_fallback: bool | None = None,
    required_fields: set[str] | tuple[str, ...] | None = None,
    extraction_policy: dict[str, Any] | None = None,
    html_collector: HtmlCollector | None = None,
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

    selected = (
        _policy_strategies(extraction_policy)
        if extraction_policy is not None
        else _legacy_strategies(
            has_css=bool(css_schema and detect_schema_type(css_schema) == "CSS"),
            enable_regex=config.crawler.enable_fit_markdown_regex,
            enable_fit_llm=fit_markdown_llm_enabled,
            enable_full_llm=llm_enabled,
        )
    )
    strategies = []

    for strategy_name in selected:
        if strategy_name == "xpath":
            strategies.append(XPathStrategy(config=config.crawler, schema=xpath_schema))
        elif strategy_name == "css":
            if not css_schema or detect_schema_type(css_schema) != "CSS":
                if len(selected) == 1:
                    raise ValueError("selected CSS strategy requires a valid CSS schema")
                logger.warning("crawler_invalid_css_schema_skipped fallbacks=%s", selected)
                continue
            strategies.append(CssStrategy(schema=css_schema))
        elif strategy_name == "fit_markdown_regex":
            strategies.append(FitMarkdownRegexStrategy(fields=config.fields))
        elif strategy_name == "fit_markdown_llm":
            strategy = FitMarkdownLlmStrategy(
                fields=config.fields,
                llm_config=config.llm,
            )
            strategy.enabled = True
            strategies.append(strategy)
        elif strategy_name == "llm_full_html":
            strategy = LlmFullHtmlStrategy(
                config=config.crawler,
                fields=config.fields,
                llm_config=config.llm,
            )
            strategy.enabled = True
            strategies.append(strategy)

    return CrawlEngine(
        config=config.crawler,
        required_fields=REQUIRED_FIELDS if required_fields is None else required_fields,
        strategies=strategies,
        html_collector=html_collector,
    )


def _policy_strategies(policy: dict[str, Any]) -> tuple[str, ...]:
    raw = policy.get("strategies")
    if not isinstance(raw, list) or not raw:
        raise ValueError("extraction policy must select at least one strategy")
    if any(not isinstance(item, str) for item in raw):
        raise ValueError("extraction policy strategies must be strings")
    if len(raw) != len(set(raw)):
        raise ValueError("extraction policy cannot repeat strategies")
    unknown = [item for item in raw if item not in CANONICAL_EXTRACTION_STRATEGIES]
    if unknown:
        raise ValueError(f"unknown extraction strategies: {', '.join(unknown)}")

    canonical = tuple(
        item for item in CANONICAL_EXTRACTION_STRATEGIES if item in raw
    )
    if tuple(raw) != canonical:
        raise ValueError("extraction policy must preserve canonical strategy order")
    return canonical


def _legacy_strategies(
    *,
    has_css: bool,
    enable_regex: bool,
    enable_fit_llm: bool,
    enable_full_llm: bool,
) -> tuple[str, ...]:
    selected = ["xpath"]
    if has_css:
        selected.append("css")
    if enable_regex:
        selected.append("fit_markdown_regex")
    if enable_fit_llm:
        selected.append("fit_markdown_llm")
    if enable_full_llm:
        selected.append("llm_full_html")
    return tuple(selected)
