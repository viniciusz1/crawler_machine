from __future__ import annotations

import pytest

from crawler_machine.extraction.factory import build_crawl_engine
from crawler_machine.config import CrawlerConfig, DiscoveryConfig, DomainConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.strategies import (
    CssStrategy,
    FitMarkdownLlmStrategy,
    FitMarkdownRegexStrategy,
    LlmFullHtmlStrategy,
    XPathStrategy,
)


@pytest.fixture
def domain_config():
    return DomainConfig(
        llm=LLMConfig(
            provider="deepseek/deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        crawler=CrawlerConfig(
            page_timeout=30000,
            max_concurrent=5,
            chunk_size=50,
            chunk_delay=0.0,
            headless=True,
        ),
        discovery=DiscoveryConfig(max_urls=100),
        fields=[
            FieldConfig(name="valor", description="Valor", coerce="currency"),
            FieldConfig(name="bairro", description="Bairro", coerce="string"),
        ],
    )


def test_build_crawl_engine_enables_xpath_css_and_fit_markdown_regex_by_default(domain_config):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "body"},
        }
    }

    engine = build_crawl_engine(config=domain_config, schema=schema)

    names = [s.name for s in engine._strategies]
    assert names == ["xpath", "css", "fit_markdown_regex"]
    assert isinstance(engine._strategies[0], XPathStrategy)
    assert isinstance(engine._strategies[1], CssStrategy)
    assert isinstance(engine._strategies[2], FitMarkdownRegexStrategy)


def test_build_crawl_engine_can_enable_llm_strategies(domain_config):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "body"},
        }
    }
    config = DomainConfig(
        llm=domain_config.llm,
        crawler=CrawlerConfig(
            page_timeout=30000,
            max_concurrent=5,
            chunk_size=50,
            chunk_delay=0.0,
            headless=True,
            enable_fit_markdown_llm=True,
            enable_llm_fallback=True,
        ),
        discovery=domain_config.discovery,
        fields=domain_config.fields,
    )

    engine = build_crawl_engine(config=config, schema=schema)

    names = [s.name for s in engine._strategies]
    assert names == [
        "xpath",
        "css",
        "fit_markdown_regex",
        "fit_markdown_llm",
        "llm_full_html",
    ]
    assert isinstance(engine._strategies[3], FitMarkdownLlmStrategy)
    assert isinstance(engine._strategies[4], LlmFullHtmlStrategy)


def test_build_crawl_engine_cli_flag_overrides_config(domain_config):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "body"},
        }
    }

    engine = build_crawl_engine(
        config=domain_config,
        schema=schema,
        enable_llm_fallback=True,
    )

    names = [s.name for s in engine._strategies]
    assert "llm_full_html" in names


def test_build_crawl_engine_handles_legacy_single_schema(domain_config):
    schema = {"name": "items", "baseSelector": "//body"}

    engine = build_crawl_engine(config=domain_config, schema=schema)

    names = [s.name for s in engine._strategies]
    assert names == ["xpath", "css", "fit_markdown_regex"]
