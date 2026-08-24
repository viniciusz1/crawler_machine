from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from crawler_machine.worker.adapters import ConfiguredProfileExtractor


def test_configured_extractor_builds_one_engine_for_all_urls(monkeypatch) -> None:
    urls = ["https://example.com/1", "https://example.com/2"]
    captured: dict[str, Any] = {}

    class FakeEngine:
        def crawl_many_sync(self, requested_urls: list[str]):
            captured["urls"] = list(requested_urls)
            return [
                ({"url": requested_urls[0], "title": "House"}, None),
                (
                    None,
                    {"url": requested_urls[1], "error": "browser failed"},
                ),
            ]

    def fake_build_crawl_engine(
        config,
        schema,
        enable_llm_fallback=None,
        required_fields=None,
        extraction_policy=None,
        html_collector=None,
    ):
        captured["config"] = config
        captured["schema"] = schema
        captured["required_fields"] = required_fields
        captured["extraction_policy"] = extraction_policy
        return FakeEngine()

    monkeypatch.setattr(
        "crawler_machine.worker.adapters.build_crawl_engine",
        fake_build_crawl_engine,
    )
    config = SimpleNamespace(
        llm=SimpleNamespace(),
        crawler=SimpleNamespace(),
        discovery=SimpleNamespace(),
    )
    policy = {"strategies": ["xpath"]}
    extractor = ConfiguredProfileExtractor(config)

    results = extractor.extract_many(
        urls,
        schemas={"xpath": {"baseSelector": "//body"}},
        fields=[{"name": "title", "required": True}],
        extraction_policy=policy,
    )

    assert captured["urls"] == urls
    assert captured["required_fields"] == {"title"}
    assert captured["extraction_policy"] is policy
    assert results == [
        ({"url": urls[0], "title": "House"}, []),
        (None, ["browser failed"]),
    ]
