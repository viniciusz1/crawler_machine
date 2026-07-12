from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.llm_full_html import LlmFullHtmlStrategy


@pytest.fixture
def fields():
    return [
        FieldConfig(name="bairro", description="Bairro", coerce="string"),
        FieldConfig(name="cidade", description="Cidade", coerce="string"),
        FieldConfig(name="valor", description="Valor do imóvel", coerce="currency"),
        FieldConfig(name="tipo_imovel", description="Tipo do imóvel", coerce="string"),
    ]


@pytest.fixture
def llm_config():
    return LLMConfig(
        provider="deepseek/deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )


@pytest.mark.anyio
async def test_llm_full_html_strategy_extracts_data(fields, llm_config):
    async def fake_crawl(url: str, instruction: str, schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "bairro": "Centro",
            "cidade": "Jaraguá",
            "valor": "R$ 500.000,00",
            "tipo_imovel": "Casa",
        }

    strategy = LlmFullHtmlStrategy(
        config=None,
        fields=fields,
        llm_config=llm_config,
        crawl_and_extract=fake_crawl,
    )

    result = await strategy.extract(
        "https://example.com/1",
        CrawlResult(url="https://example.com/1", success=True, data=[], html="<html></html>"),
    )

    assert result.success
    assert len(result.data) == 1
    assert result.data[0]["bairro"] == "Centro"
    assert result.data[0]["cidade"] == "Jaraguá"


@pytest.mark.anyio
async def test_llm_full_html_strategy_disabled_by_default(fields, llm_config):
    strategy = LlmFullHtmlStrategy(config=None, fields=fields, llm_config=llm_config)
    assert not strategy.enabled


@pytest.mark.anyio
async def test_llm_full_html_strategy_returns_error_on_failure(fields, llm_config):
    async def fake_crawl(url: str, instruction: str, schema: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("LLM failed")

    strategy = LlmFullHtmlStrategy(
        config=None,
        fields=fields,
        llm_config=llm_config,
        crawl_and_extract=fake_crawl,
    )

    result = await strategy.extract(
        "https://example.com/1",
        CrawlResult(url="https://example.com/1", success=True, data=[], html="<html></html>"),
    )

    assert not result.success
    assert "LLM failed" in (result.error or "")
