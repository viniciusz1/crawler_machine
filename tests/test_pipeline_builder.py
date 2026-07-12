from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from crawler_machine.config import CrawlerConfig, DiscoveryConfig, DomainConfig, FieldConfig, LLMConfig
from crawler_machine.output import OutputPath
from crawler_machine.pipeline import Pipeline
from crawler_machine.pipeline.builder import build_pipeline
from crawler_machine.sink import RunStore


@pytest.fixture
def config():
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
            chunk_delay=2.0,
            headless=True,
        ),
        discovery=DiscoveryConfig(max_urls=500),
        fields=[
            FieldConfig(name="quartos", description="Número de quartos", coerce="int")
        ],
    )


@pytest.fixture
def output(tmp_path: Path):
    return OutputPath(base_dir=tmp_path, domain="example.com", timestamp="20260702_120000")


def test_build_pipeline_returns_configured_pipeline(config, output):
    pipeline = build_pipeline(
        config=config,
        output=output,
        source_name="imob-test",
    )

    assert isinstance(pipeline, Pipeline)


def test_build_pipeline_passes_sink_and_catalog_repository(config, output):
    sink = MagicMock(spec=RunStore)
    sink.catalog_repository.return_value = MagicMock(name="catalog")

    pipeline = build_pipeline(
        config=config,
        output=output,
        source_name="imob-test",
        sink=sink,
    )

    assert pipeline._sink is sink
    assert pipeline._catalog_repository is sink.catalog_repository.return_value
    sink.catalog_repository.assert_called_once_with()


def test_build_pipeline_passes_progress_callback(config, output):
    def progress(step: str, percent: int, message: str) -> None:
        pass

    pipeline = build_pipeline(
        config=config,
        output=output,
        source_name="imob-test",
        progress_callback=progress,
    )

    assert pipeline._progress_callback is progress


def test_build_pipeline_passes_llm_fallback(config, output):
    pipeline = build_pipeline(
        config=config,
        output=output,
        source_name="imob-test",
        enable_llm_fallback=True,
    )

    crawler = pipeline._crawler_factory({})
    assert crawler is not None
