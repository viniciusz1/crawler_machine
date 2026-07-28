from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.crawl4ai_llm_client import (
    Crawl4AILlmClient,
)
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
    async def fake_crawl(
        url: str,
        html: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        assert html == "<html></html>"
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
    async def fake_crawl(
        url: str,
        html: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
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


@pytest.mark.anyio
async def test_llm_full_html_requests_only_missing_fields(fields, llm_config):
    calls: list[tuple[str, set[str]]] = []

    async def fake_crawl(
        url: str,
        html: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        calls.append((html, set(schema["properties"])))
        return {"cidade": "Jaraguá"}

    strategy = LlmFullHtmlStrategy(
        config=None,
        fields=fields,
        llm_config=llm_config,
        crawl_and_extract=fake_crawl,
    )
    previous = CrawlResult(
        url="https://example.com/1",
        success=True,
        data=[
            {
                "bairro": "Centro",
                "valor": "R$ 500.000,00",
                "tipo_imovel": "Casa",
            }
        ],
        html="<html>collected once</html>",
    )

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success is True
    assert result.data == [{"cidade": "Jaraguá"}]
    assert calls == [("<html>collected once</html>", {"cidade"})]


@pytest.mark.anyio
async def test_llm_full_html_does_not_call_provider_when_fields_are_complete(
    fields,
    llm_config,
):
    called = False

    async def fake_crawl(
        url: str,
        html: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        return {}

    strategy = LlmFullHtmlStrategy(
        config=None,
        fields=fields,
        llm_config=llm_config,
        crawl_and_extract=fake_crawl,
    )
    previous = CrawlResult(
        url="https://example.com/1",
        success=True,
        data=[
            {
                "bairro": "Centro",
                "cidade": "Jaraguá",
                "valor": 500_000,
                "tipo_imovel": "Casa",
            }
        ],
        html="<html></html>",
    )

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success is True
    assert result.data == []
    assert called is False


@pytest.mark.anyio
async def test_crawl4ai_llm_client_processes_collected_html_without_browser(
    llm_config,
    monkeypatch,
):
    calls: list[tuple[str, list[str]]] = []

    class FakeLlmExtractionStrategy:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["provider"] == llm_config.provider

        def run(self, url: str, sections: list[str]) -> list[dict[str, Any]]:
            calls.append((url, sections))
            return [
                {
                    "cidade": "Jaraguá",
                    "ignored": "not in schema",
                    "error": False,
                }
            ]

    monkeypatch.setattr(
        "crawler_machine.extraction.strategies.crawl4ai_llm_client.LLMExtractionStrategy",
        FakeLlmExtractionStrategy,
    )
    client = Crawl4AILlmClient(llm_config)

    result = await client.extract(
        "https://example.com/1",
        "<html>already collected</html>",
        "Extract city",
        {
            "type": "object",
            "properties": {"cidade": {"type": ["string", "null"]}},
        },
    )

    assert result == {"cidade": "Jaraguá"}
    assert calls == [
        (
            "https://example.com/1",
            ["<html>already collected</html>"],
        )
    ]
