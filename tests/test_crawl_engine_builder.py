from __future__ import annotations

from itertools import combinations

import pytest

from crawler_machine.extraction.factory import (
    CANONICAL_EXTRACTION_STRATEGIES,
    build_crawl_engine,
)
from crawler_machine.config import CrawlerConfig, DiscoveryConfig, DomainConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies import (
    CssStrategy,
    FitMarkdownLlmStrategy,
    FitMarkdownRegexStrategy,
    LlmFullHtmlStrategy,
    XPathStrategy,
)

ALL_POLICY_SUBSETS = [
    list(subset)
    for length in range(1, len(CANONICAL_EXTRACTION_STRATEGIES) + 1)
    for subset in combinations(CANONICAL_EXTRACTION_STRATEGIES, length)
]


class FakeHtmlCollector:
    def __init__(self, html: str) -> None:
        self._html = html
        self.calls: list[str] = []

    async def run(self, url: str) -> CrawlResult:
        self.calls.append(url)
        return CrawlResult(
            url=url,
            success=True,
            data=[],
            html=self._html,
            images=["https://example.com/image.jpg"],
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
    assert names == ["xpath", "fit_markdown_regex"]


def test_build_crawl_engine_skips_css_when_css_schema_uses_xpath(domain_config):
    """Regressão: schemas CSS gerados com seletores XPath não devem ativar CssStrategy."""
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//div[@class='imovel']"},
            "css": {"name": "items", "baseSelector": "//ul[@data-template='']/li"},
        }
    }

    engine = build_crawl_engine(config=domain_config, schema=schema)

    names = [s.name for s in engine._strategies]
    assert "css" not in names
    assert names == ["xpath", "fit_markdown_regex"]


@pytest.mark.parametrize("selected", ALL_POLICY_SUBSETS)
def test_build_crawl_engine_constructs_every_valid_policy_subset(
    domain_config,
    selected,
):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "body"},
        }
    }

    engine = build_crawl_engine(
        config=domain_config,
        schema=schema,
        extraction_policy={
            "id": "immutable-policy-version",
            "version": 7,
            "strategies": selected,
            "configuration": {
                "max_concurrent": 999,
                "page_timeout": 1,
                "retry_attempts": 99,
                "cache_mode": "BYPASS",
                "provider": "attacker/provider",
                "api_key": "must-not-be-used",
            },
        },
    )

    assert [strategy.name for strategy in engine._strategies] == selected
    assert engine._config is domain_config.crawler


@pytest.mark.anyio
async def test_css_policy_runs_without_xpath_on_the_single_collected_html(
    domain_config,
):
    collector = FakeHtmlCollector(
        """
        <html><body>
          <article class="property"><span class="district">Centro</span></article>
        </body></html>
        """
    )
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {
                "name": "items",
                "baseSelector": "article.property",
                "fields": [
                    {
                        "name": "bairro",
                        "selector": "span.district",
                        "type": "text",
                    }
                ],
            },
        }
    }
    engine = build_crawl_engine(
        config=domain_config,
        schema=schema,
        required_fields={"bairro"},
        extraction_policy={"strategies": ["css"]},
        html_collector=collector,
    )

    records, errors = await engine.crawl(["https://example.com/property/1"])

    assert errors == []
    assert records[0]["bairro"] == "Centro"
    assert records[0]["_extraction_trace"] == {"bairro": "css"}
    assert collector.calls == ["https://example.com/property/1"]


@pytest.mark.parametrize(
    "strategies",
    [
        [],
        ["css", "xpath"],
        ["xpath", "xpath"],
        ["unknown"],
    ],
)
def test_build_crawl_engine_rejects_invalid_policy_strategies(
    domain_config,
    strategies,
):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "body"},
        }
    }

    with pytest.raises(ValueError):
        build_crawl_engine(
            config=domain_config,
            schema=schema,
            extraction_policy={"strategies": strategies},
        )


def test_selected_css_requires_a_css_schema(domain_config):
    schema = {
        "schemas": {
            "xpath": {"name": "items", "baseSelector": "//body"},
            "css": {"name": "items", "baseSelector": "//body"},
        }
    }

    with pytest.raises(ValueError, match="valid CSS schema"):
        build_crawl_engine(
            config=domain_config,
            schema=schema,
            extraction_policy={"strategies": ["css"]},
        )
