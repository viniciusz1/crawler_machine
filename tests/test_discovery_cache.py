import pytest
from unittest.mock import MagicMock

from crawler_machine.pipeline.discovery_cache import DiscoveryCache


@pytest.mark.anyio
async def test_discovery_cache_load_returns_none_when_regenerate():
    sink = MagicMock()
    cache = DiscoveryCache(sink)

    result = await cache.load("source", regenerate=True)

    assert result is None
    sink.load_latest_discovery.assert_not_called()


@pytest.mark.anyio
async def test_discovery_cache_load_queries_sink():
    sink = MagicMock()
    sink.load_latest_discovery.return_value = ["https://example.com/1"]
    cache = DiscoveryCache(sink)

    result = await cache.load("source", regenerate=False)

    assert result == ["https://example.com/1"]
    sink.load_latest_discovery.assert_called_once_with("source")


@pytest.mark.anyio
async def test_discovery_cache_save_returns_run_id():
    sink = MagicMock()
    sink.save_discovery_run.return_value = 7
    cache = DiscoveryCache(sink)

    run_id = await cache.save("source", ["https://example.com/1"])

    assert run_id == 7
    sink.save_discovery_run.assert_called_once_with("source", ["https://example.com/1"])


@pytest.mark.anyio
async def test_discovery_cache_save_returns_none_without_sink():
    cache = DiscoveryCache(None)

    run_id = await cache.save("source", ["https://example.com/1"])

    assert run_id is None
