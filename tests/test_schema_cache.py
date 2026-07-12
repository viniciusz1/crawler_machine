from typing import Any

import pytest
from unittest.mock import MagicMock

from crawler_machine.pipeline.schema_cache import SchemaCache


def _schema() -> dict[str, Any]:
    return {
        "metadata": {"sample_url": "https://example.com/1"},
        "schemas": {
            "xpath": {"name": "XPathSchema", "baseSelector": "//body"},
            "css": {"name": "CSSSchema", "baseSelector": "body"},
        },
    }


@pytest.mark.anyio
async def test_schema_cache_load_returns_none_when_regenerate():
    sink = MagicMock()
    cache = SchemaCache(sink)

    result = await cache.load("source", regenerate=True)

    assert result is None
    sink.load_latest_schema.assert_not_called()


@pytest.mark.anyio
async def test_schema_cache_load_queries_sink():
    sink = MagicMock()
    sink.load_latest_schema.return_value = {"name": "Cached"}
    cache = SchemaCache(sink)

    result = await cache.load("source", regenerate=False)

    assert result == {"name": "Cached"}
    sink.load_latest_schema.assert_called_once_with("source")


@pytest.mark.anyio
async def test_schema_cache_save_dual_schemas():
    sink = MagicMock()
    sink.save_schema_run.return_value = 5
    cache = SchemaCache(sink)

    last_id = await cache.save("source", _schema(), "https://example.com/1")

    assert last_id == 5
    assert sink.save_schema_run.call_count == 2
    calls = sink.save_schema_run.call_args_list
    assert calls[0][0][1] == {"name": "XPathSchema", "baseSelector": "//body"}
    assert calls[0][0][2] == "XPATH"
    assert calls[1][0][1] == {"name": "CSSSchema", "baseSelector": "body"}
    assert calls[1][0][2] == "CSS"


@pytest.mark.anyio
async def test_schema_cache_save_single_schema():
    sink = MagicMock()
    sink.save_schema_run.return_value = 3
    cache = SchemaCache(sink)

    last_id = await cache.save("source", {"name": "Single"}, "https://example.com/1")

    assert last_id == 3
    sink.save_schema_run.assert_called_once()


@pytest.mark.anyio
async def test_schema_cache_save_returns_none_without_sink():
    cache = SchemaCache(None)

    last_id = await cache.save("source", _schema(), "https://example.com/1")

    assert last_id is None
