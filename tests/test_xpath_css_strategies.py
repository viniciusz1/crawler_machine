from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies.css import CssStrategy
from crawler_machine.extraction.strategies.http_runner import HttpRunner
from crawler_machine.extraction.strategies.xpath import XPathStrategy


HTML = """
<html>
<body>
    <div class="imovel">
        <h1 class="titulo">Casa no Centro</h1>
        <span class="preco">R$ 450.000,00</span>
        <span class="bairro">Centro</span>
        <span class="cidade">Jaraguá</span>
        <span class="tipo">Casa</span>
        <img src="https://example.com/img.jpg" />
    </div>
</body>
</html>
"""


@pytest.fixture
def crawler_config():
    return CrawlerConfig(
        page_timeout=30000,
        max_concurrent=5,
        chunk_size=50,
        chunk_delay=0.0,
        headless=True,
        retry_attempts=1,
    )


def _make_runner(html: str | None = HTML):
    async def runner(url: str) -> CrawlResult:
        if html is None:
            return CrawlResult(url=url, success=False, data=[], error="fetch failed")
        return CrawlResult(url=url, success=True, data=[], html=html)

    return runner


@pytest.mark.anyio
async def test_xpath_strategy_fetches_and_extracts(crawler_config):
    schema = {
        "name": "items",
        "baseSelector": "//div[@class='imovel']",
        "fields": [
            {"name": "titulo", "selector": "//h1[@class='titulo']", "type": "text"},
            {"name": "valor", "selector": "//span[@class='preco']", "type": "text"},
        ],
    }
    strategy = XPathStrategy(
        config=crawler_config, schema=schema, http_runner=HttpRunner(crawler_config, fetch=_make_runner())
    )

    result = await strategy.extract("https://example.com/1", None)

    assert result.success
    assert len(result.data) == 1
    assert "R$ 450.000,00" in result.data[0].get("valor", "")
    assert result.html == HTML


@pytest.mark.anyio
async def test_xpath_strategy_reuses_previous_html(crawler_config):
    schema = {
        "name": "items",
        "baseSelector": "//div[@class='imovel']",
        "fields": [
            {"name": "valor", "selector": "//span[@class='preco']", "type": "text"},
        ],
    }
    calls: list[str] = []

    async def tracking_runner(url: str) -> CrawlResult:
        calls.append(url)
        return CrawlResult(url=url, success=True, data=[], html=HTML)

    strategy = XPathStrategy(
        config=crawler_config,
        schema=schema,
        http_runner=HttpRunner(crawler_config, fetch=tracking_runner),
    )
    previous = CrawlResult(url="https://example.com/1", success=True, data=[], html=HTML)

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success
    assert len(result.data) == 1
    assert calls == []


@pytest.mark.anyio
async def test_css_strategy_extracts_from_previous_html(crawler_config):
    schema = {
        "name": "items",
        "baseSelector": "div.imovel",
        "fields": [
            {"name": "valor", "selector": "span.preco", "type": "text"},
            {"name": "bairro", "selector": "span.bairro", "type": "text"},
        ],
    }
    strategy = CssStrategy(schema=schema)
    previous = CrawlResult(url="https://example.com/1", success=True, data=[], html=HTML)

    result = await strategy.extract("https://example.com/1", previous)

    assert result.success
    assert len(result.data) == 1
    assert "R$ 450.000,00" in result.data[0].get("valor", "")
    assert result.data[0].get("bairro") == "Centro"


@pytest.mark.anyio
async def test_css_strategy_fails_without_previous_html(crawler_config):
    schema = {
        "name": "items",
        "baseSelector": "div.imovel",
        "fields": [{"name": "valor", "selector": "span.preco", "type": "text"}],
    }
    strategy = CssStrategy(schema=schema)

    result = await strategy.extract("https://example.com/1", None)

    assert not result.success
    assert "html" in (result.error or "").lower()


@pytest.mark.anyio
async def test_http_runner_retries_on_transient_error(crawler_config, monkeypatch):
    attempts: list[int] = []

    async def flaky_runner(url: str) -> CrawlResult:
        attempts.append(len(attempts))
        if len(attempts) < 2:
            return CrawlResult(
                url=url, success=False, data=[], error="Page.goto: Timeout 30000ms exceeded"
            )
        return CrawlResult(url=url, success=True, data=[], html=HTML)

    config = CrawlerConfig(
        page_timeout=30000,
        max_concurrent=5,
        chunk_size=50,
        chunk_delay=0.0,
        headless=True,
        retry_attempts=3,
        retry_base_delay=0.01,
    )
    runner = HttpRunner(config, fetch=flaky_runner)

    result = await runner.run("https://example.com/1")

    assert result.success
    assert result.html == HTML
    assert len(attempts) == 2
