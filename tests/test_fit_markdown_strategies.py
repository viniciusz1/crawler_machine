from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.fit_markdown_llm import FitMarkdownLlmStrategy
from crawler_machine.extraction.strategies.fit_markdown_regex import FitMarkdownRegexStrategy


HTML = """
<html><body>
<div class="imovel">
<h1>Casa à venda no Centro - Jaraguá</h1>
<p>Valor: R$ 450.000,00</p>
<p>3 quartos, 2 suítes</p>
<p>Área construída: 120 m²</p>
<img src="https://example.com/img.jpg" />
</div>
</body></html>
"""

MARKDOWN = """
# Casa à venda no Centro - Jaraguá

Valor: R$ 450.000,00
3 quartos, 2 suítes
Área construída: 120 m²
"""


class FakeMarkdownGenerator:
    def __init__(self, fit_markdown: str = MARKDOWN):
        self._fit_markdown = fit_markdown

    def generate_markdown(
        self,
        input_html: str,
        base_url: str = "",
        **kwargs: Any,
    ) -> Any:
        return FakeMarkdownResult(self._fit_markdown)


class FakeMarkdownResult:
    def __init__(self, fit_markdown: str):
        self.fit_markdown = fit_markdown
        self.raw_markdown = fit_markdown


@pytest.fixture
def fields():
    return [
        FieldConfig(name="valor", description="Valor do imóvel", coerce="currency"),
        FieldConfig(name="quartos", description="Número de quartos", coerce="int"),
        FieldConfig(name="area", description="Área do imóvel", coerce="int"),
        FieldConfig(name="imagem", description="URL da imagem", coerce="string"),
        FieldConfig(name="bairro", description="Bairro", coerce="string"),
        FieldConfig(name="cidade", description="Cidade", coerce="string"),
        FieldConfig(name="tipo_imovel", description="Tipo do imóvel", coerce="string"),
    ]


@pytest.mark.anyio
async def test_fit_markdown_regex_extracts_price_rooms_and_area(fields):
    strategy = FitMarkdownRegexStrategy(
        fields=fields,
        markdown_generator=FakeMarkdownGenerator(),
    )
    previous = CrawlResult(
        url="https://example.com/1", success=True, data=[], html=HTML
    )

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success
    assert len(result.data) == 1
    assert result.data[0].get("valor") == 450_000.0
    assert result.data[0].get("quartos") == 3
    assert result.data[0].get("area") == 120


@pytest.mark.anyio
async def test_fit_markdown_regex_requires_html(fields):
    strategy = FitMarkdownRegexStrategy(fields=fields)

    result = await strategy.extract("https://example.com/1", None)

    assert not result.success
    assert "html" in (result.error or "").lower()


@pytest.mark.anyio
async def test_fit_markdown_regex_returns_empty_when_no_patterns_match(fields):
    strategy = FitMarkdownRegexStrategy(
        fields=fields,
        markdown_generator=FakeMarkdownGenerator("apenas texto sem dados"),
    )
    previous = CrawlResult(
        url="https://example.com/1", success=True, data=[], html=HTML
    )

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success
    # imagem é extraída do HTML independentemente de regex
    assert result.data == [{"imagem": "https://example.com/img.jpg"}]


@pytest.mark.anyio
async def test_fit_markdown_llm_extracts_missing_fields(fields):
    async def fake_extract(url: str, markdown: str, missing: set[str]) -> dict[str, Any]:
        return {
            "bairro": "Centro",
            "cidade": "Jaraguá",
            "tipo_imovel": "Casa",
        }

    strategy = FitMarkdownLlmStrategy(
        fields=fields,
        llm_config=LLMConfig(
            provider="deepseek/deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        markdown_generator=FakeMarkdownGenerator(),
        extract_missing=fake_extract,
    )
    previous = CrawlResult(
        url="https://example.com/1", success=True, data=[], html=HTML
    )

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success
    assert len(result.data) == 1
    assert result.data[0].get("bairro") == "Centro"
    assert result.data[0].get("cidade") == "Jaraguá"
    assert result.data[0].get("tipo_imovel") == "Casa"


@pytest.mark.anyio
async def test_fit_markdown_llm_requires_html(fields):
    strategy = FitMarkdownLlmStrategy(
        fields=fields,
        llm_config=LLMConfig(
            provider="deepseek/deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        ),
    )

    result = await strategy.extract("https://example.com/1", None)

    assert not result.success
    assert "html" in (result.error or "").lower()
