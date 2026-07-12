from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import CrawlerConfig, FieldConfig
from crawler_machine.extraction.engine import CrawlEngine
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategy import ExtractionStrategy


REQUIRED_FIELDS = {"bairro", "cidade", "valor", "tipo_imovel", "url", "imagem"}


class FakeStrategy(ExtractionStrategy):
    def __init__(
        self,
        name: str,
        enabled: bool = True,
        returns: dict[str, dict[str, Any]] | None = None,
        expects_html: bool = False,
    ):
        self.name = name
        self.enabled = enabled
        self.returns = returns or {}
        self.calls: list[tuple[str, CrawlResult | None]] = []
        self.expects_html = expects_html

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        self.calls.append((url, previous))
        if self.expects_html and (previous is None or not previous.html):
            return CrawlResult(url=url, success=True, data=[])
        payload = self.returns.get(url, {})
        return CrawlResult(
            url=url,
            success=True,
            data=[dict(payload)],
            html=previous.html if previous else f"<html>{url}</html>",
        )


class ErrorStrategy(ExtractionStrategy):
    name = "error"
    enabled = True

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        return CrawlResult(url=url, success=False, data=[], error="boom")


@pytest.fixture
def crawler_config():
    return CrawlerConfig(
        page_timeout=30000,
        max_concurrent=5,
        chunk_size=2,
        chunk_delay=0.0,
        headless=True,
    )


@pytest.mark.anyio
async def test_engine_runs_strategies_in_order_and_fills_missing_fields(crawler_config):
    strategy_a = FakeStrategy(
        "a",
        returns={
            "https://example.com/1": {"bairro": "Centro", "cidade": "Jaraguá"},
        },
    )
    strategy_b = FakeStrategy(
        "b",
        returns={
            "https://example.com/1": {"valor": 450_000.0, "tipo_imovel": "Casa"},
        },
        expects_html=True,
    )

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a, strategy_b],
    )

    results, errors = await engine.crawl(["https://example.com/1"])

    assert errors == []
    assert len(results) == 1
    assert results[0]["bairro"] == "Centro"
    assert results[0]["cidade"] == "Jaraguá"
    assert results[0]["valor"] == 450_000.0
    assert results[0]["tipo_imovel"] == "Casa"
    assert results[0]["url"] == "https://example.com/1"
    assert results[0]["_extraction_trace"] == {
        "bairro": "a",
        "cidade": "a",
        "valor": "b",
        "tipo_imovel": "b",
        "url": "url",
    }
    assert strategy_b.calls[0][1].html == "<html>https://example.com/1</html>"


@pytest.mark.anyio
async def test_engine_stops_when_all_required_fields_are_present(crawler_config):
    strategy_a = FakeStrategy(
        "a",
        returns={
            "https://example.com/1": {
                "bairro": "Centro",
                "cidade": "Jaraguá",
                "valor": 100_000.0,
                "tipo_imovel": "Casa",
                "imagem": "https://example.com/img.jpg",
            },
        },
    )
    strategy_b = FakeStrategy("b", returns={"https://example.com/1": {"extra": "x"}})

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a, strategy_b],
    )

    results, _ = await engine.crawl(["https://example.com/1"])

    assert len(results) == 1
    assert "extra" not in results[0]
    assert len(strategy_b.calls) == 0


@pytest.mark.anyio
async def test_engine_skips_disabled_strategies(crawler_config):
    strategy_a = FakeStrategy("a", enabled=False)
    strategy_b = FakeStrategy(
        "b",
        returns={"https://example.com/1": {"bairro": "Centro"}},
    )

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a, strategy_b],
    )

    results, _ = await engine.crawl(["https://example.com/1"])

    assert len(strategy_a.calls) == 0
    assert len(strategy_b.calls) == 1
    assert results[0]["bairro"] == "Centro"


@pytest.mark.anyio
async def test_engine_continues_when_early_strategy_fails(crawler_config):
    strategy_a = ErrorStrategy()
    strategy_b = FakeStrategy(
        "b",
        returns={"https://example.com/1": {"bairro": "Centro"}},
    )

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a, strategy_b],
    )

    results, errors = await engine.crawl(["https://example.com/1"])

    assert len(results) == 1
    assert results[0]["bairro"] == "Centro"
    assert errors == []


@pytest.mark.anyio
async def test_engine_returns_partial_records_when_strategies_exhausted(crawler_config):
    strategy_a = FakeStrategy(
        "a",
        returns={"https://example.com/1": {"bairro": "Centro"}},
    )

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a],
    )

    results, errors = await engine.crawl(["https://example.com/1"])

    assert errors == []
    assert len(results) == 1
    assert results[0]["bairro"] == "Centro"
    assert "cidade" not in results[0]


@pytest.mark.anyio
async def test_engine_chunks_urls_and_respects_delay(monkeypatch):
    sleeps: list[float] = []
    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(
        "crawler_machine.extraction.engine.asyncio.sleep", fake_sleep
    )
    config = CrawlerConfig(
        page_timeout=30000,
        max_concurrent=5,
        chunk_size=2,
        chunk_delay=1.5,
        headless=True,
    )
    strategy = FakeStrategy(
        "a",
        returns={f"https://example.com/{i}": {"bairro": f"Bairro {i}"} for i in range(3)},
    )

    engine = CrawlEngine(
        config=config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy],
    )

    results, _ = await engine.crawl([f"https://example.com/{i}" for i in range(3)])

    assert len(results) == 3
    assert len(sleeps) == 1
    assert sleeps[0] == 1.5


@pytest.mark.anyio
async def test_strategy_does_not_overwrite_already_found_fields(crawler_config):
    strategy_a = FakeStrategy(
        "a",
        returns={"https://example.com/1": {"bairro": "Centro", "valor": 100_000.0}},
    )
    strategy_b = FakeStrategy(
        "b",
        returns={"https://example.com/1": {"bairro": "Outro", "valor": 200_000.0}},
    )

    engine = CrawlEngine(
        config=crawler_config,
        required_fields=REQUIRED_FIELDS,
        strategies=[strategy_a, strategy_b],
    )

    results, _ = await engine.crawl(["https://example.com/1"])

    assert results[0]["bairro"] == "Centro"
    assert results[0]["valor"] == 100_000.0


def test_crawl_result_defaults():
    result = CrawlResult(url="https://example.com", success=True, data=[])
    assert result.images == []
    assert result.html is None
    assert result.error is None


def test_required_fields_set_is_exposed():
    from crawler_machine.extraction.engine import REQUIRED_FIELDS as EngineRequired

    assert EngineRequired == REQUIRED_FIELDS
