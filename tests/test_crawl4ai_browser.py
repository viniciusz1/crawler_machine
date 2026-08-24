from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.strategies.crawl4ai_browser import Crawl4AIBrowser


@pytest.mark.anyio
async def test_browser_uses_one_arun_many_call_and_preserves_input_order(
    monkeypatch,
):
    urls = ["https://example.com/1", "https://example.com/2"]
    instances: list[Any] = []

    class FakeAsyncWebCrawler:
        def __init__(self, config):
            self.browser_config = config
            self.calls: list[dict[str, Any]] = []
            instances.append(self)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def arun_many(self, *, urls, config, dispatcher):
            self.calls.append(
                {"urls": list(urls), "config": config, "dispatcher": dispatcher}
            )
            return [
                SimpleNamespace(
                    url=url,
                    success=True,
                    html=f"<html>{url}</html>",
                    media={"images": [{"src": f"{url}/image.jpg"}]},
                    error_message=None,
                )
                for url in reversed(urls)
            ]

    monkeypatch.setattr(
        "crawler_machine.extraction.strategies.crawl4ai_browser.AsyncWebCrawler",
        FakeAsyncWebCrawler,
    )
    config = CrawlerConfig(
        page_timeout=30000,
        max_concurrent=5,
        chunk_size=50,
        chunk_delay=0.0,
        headless=True,
        mean_delay=0.5,
        max_range=1.0,
    )

    results = await Crawl4AIBrowser(config).fetch_many(urls)

    assert len(instances) == 1
    assert len(instances[0].calls) == 1
    call = instances[0].calls[0]
    assert call["urls"] == urls
    assert call["dispatcher"].max_session_permit == 5
    assert call["dispatcher"].rate_limiter is not None
    assert [result.url for result in results] == urls
    assert results[0].images == [f"{urls[0]}/image.jpg"]
