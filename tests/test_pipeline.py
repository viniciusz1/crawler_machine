import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from crawler_machine.config import CrawlerConfig, DiscoveryConfig, FieldConfig, LLMConfig
from crawler_machine.output import OutputPath
from crawler_machine.pipeline import Pipeline


class FakeDiscoverer:
    def __init__(self, urls: list[str]):
        self.urls = urls

    async def discover(self, base_url: str) -> list[str]:
        return self.urls


class FakeSchemaGenerator:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema
        self.sample_url: str | None = None

    async def generate(self, sample_url: str) -> dict[str, Any]:
        self.sample_url = sample_url
        return {
            "metadata": {"sample_url": sample_url},
            "schemas": {"xpath": self.schema, "css": self.schema},
        }


class FakeCrawler:
    def __init__(self, data: list[dict[str, Any]], errors: list[dict[str, Any]]):
        self.data = data
        self.errors = errors
        self.urls: list[str] | None = None
        self.schema: dict[str, Any] | None = None

    async def crawl(self, urls: list[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        self.urls = urls
        return self.data, self.errors


def _complete_record(**overrides: Any) -> dict[str, Any]:
    record = {
        "bairro": "Centro",
        "cidade": "Jaraguá do Sul",
        "valor": 450_000,
        "tipo_imovel": "Apartamento",
        "url": "https://example.com/imovel/1",
        "imagem": "https://example.com/imovel/1.jpg",
        "quartos": 3,
    }
    record.update(overrides)
    return record


def make_fake_crawler(schema: dict[str, Any]) -> FakeCrawler:
    return FakeCrawler(
        data=[_complete_record(quartos=3), _complete_record(quartos=2, url="https://example.com/imovel/2")],
        errors=[],
    )


@pytest.fixture
def config():
    return {
        "llm": LLMConfig(
            provider="deepseek/deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key_env="DEEPSEEK_API_KEY",
        ),
        "crawler": CrawlerConfig(
            page_timeout=30000,
            max_concurrent=5,
            chunk_size=50,
            chunk_delay=2.0,
            headless=True,
        ),
        "discovery": DiscoveryConfig(max_urls=500),
        "fields": [
            FieldConfig(name="quartos", description="Número de quartos", coerce="int")
        ],
    }


@pytest.fixture
def output(tmp_path: Path):
    return OutputPath(base_dir=tmp_path, domain="example.com", timestamp="20260702_120000")


@pytest.mark.anyio
async def test_pipeline_runs_all_steps_and_saves_artifacts(config, output):
    discoverer = FakeDiscoverer([
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ])
    schema_generator = FakeSchemaGenerator({"name": "Imovel", "baseSelector": "//body"})

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=make_fake_crawler,
        source_name="example",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/1",
    )

    assert result.normalized == [
        {
            "bairro": "Centro",
            "cidade": "Jaraguá do Sul",
            "valor": 450_000,
            "tipo_imovel": "Apartamento",
            "url": "https://example.com/imovel/1",
            "imagem": "https://example.com/imovel/1.jpg",
            "quartos": 3,
            "_quality": {"valid": True, "warnings": []},
        },
        {
            "bairro": "Centro",
            "cidade": "Jaraguá do Sul",
            "valor": 450_000,
            "tipo_imovel": "Apartamento",
            "url": "https://example.com/imovel/2",
            "imagem": "https://example.com/imovel/1.jpg",
            "quartos": 2,
            "_quality": {"valid": True, "warnings": []},
        },
    ]
    assert result.errors == []
    assert result.rejected == []
    assert result.run_id is None
    assert schema_generator.sample_url == "https://example.com/imovel/1"

    assert output.discovered.exists()
    assert output.schema.exists()
    assert output.raw.exists()
    assert output.normalized.exists()
    assert output.rejected.exists()
    assert output.quality_report.exists()

    quality_report = json.loads(output.quality_report.read_text())
    assert quality_report["exterminated_count"] == 0
    assert quality_report["extermination_reasons"] == {}

    discovered = json.loads(output.discovered.read_text())
    assert discovered["urls"] == [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ]

    schema = json.loads(output.schema.read_text())
    assert schema["schemas"]["xpath"] == {"name": "Imovel", "baseSelector": "//body"}
    assert schema["schemas"]["css"] == {"name": "Imovel", "baseSelector": "//body"}


@pytest.mark.anyio
async def test_pipeline_saves_to_sink_when_configured(config, output):
    discoverer = FakeDiscoverer([
        "https://example.com/imovel/1",
    ])
    schema_generator = FakeSchemaGenerator({"name": "Imovel"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = None
    sink.load_latest_schema.return_value = None
    sink.start_run.return_value = 7
    sink.save_run.return_value = 7
    sink.save_discovery_run.return_value = 1
    sink.save_schema_run.return_value = 2

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([_complete_record(quartos=3)], []),
        sink=sink,
        source_name="imob-test",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/1",
    )

    raw_record = _complete_record(quartos=3)
    normalized_record = {
        **raw_record,
        "quartos": 3,
        "_quality": {"valid": True, "warnings": []},
    }

    assert result.normalized == [normalized_record]
    assert result.rejected == []
    assert result.run_id == 7
    sink.start_run.assert_called_once_with("imob-test")
    assert sink.save_schema_run.call_count == 2
    sink.save_run.assert_called_once_with(
        "imob-test",
        [raw_record],
        [normalized_record],
        [],
    )


@pytest.mark.anyio
async def test_pipeline_uses_sample_url_when_provided(config, output):
    discoverer = FakeDiscoverer(["https://example.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "Imovel"})

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([], []),
        source_name="example",
    )

    await pipeline.run("https://example.com", sample_url="https://example.com/imovel/especial")

    assert schema_generator.sample_url == "https://example.com/imovel/especial"


@pytest.mark.anyio
async def test_pipeline_reuses_discovery_from_sink(config, output):
    """Quando o sink tem URLs cacheadas e regenerate_discovery=False, o discoverer não é chamado."""
    discoverer = FakeDiscoverer(["https://should-not-be-called.com"])
    schema_generator = FakeSchemaGenerator({"name": "Imovel"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = [
        "https://example.com/imovel/1",
        "https://example.com/imovel/2",
    ]
    sink.load_latest_schema.return_value = None
    sink.start_run.return_value = 1
    sink.save_run.return_value = 1

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([_complete_record(quartos=3)], []),
        sink=sink,
        source_name="imob-test",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/1",
        regenerate_discovery=False,
    )

    assert result.normalized == [
        {**_complete_record(quartos=3), "_quality": {"valid": True, "warnings": []}}
    ]
    sink.load_latest_discovery.assert_called_once_with("imob-test")
    # discoverer NÃO foi chamado porque usamos o cache
    assert discoverer.urls == ["https://should-not-be-called.com"]  # untouched


@pytest.mark.anyio
async def test_pipeline_regenerate_discovery_ignores_cache(config, output):
    """Com regenerate_discovery=True, o cache é ignorado e o discoverer é chamado."""
    discoverer = FakeDiscoverer(["https://fresh-url.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "Imovel"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = ["https://cached-url.com"]
    sink.load_latest_schema.return_value = None
    sink.start_run.return_value = 1
    sink.save_run.return_value = 1

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([_complete_record(quartos=4)], []),
        sink=sink,
        source_name="imob-test",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/1",
        regenerate_discovery=True,
    )

    assert result.normalized == [
        {**_complete_record(quartos=4), "_quality": {"valid": True, "warnings": []}}
    ]
    # load_latest_discovery NÃO foi chamado porque regenerate=True
    sink.load_latest_discovery.assert_not_called()


@pytest.mark.anyio
async def test_pipeline_reuses_schema_from_sink(config, output):
    """Quando o sink tem schema cacheado e regenerate_schema=False, o schema generator não é chamado."""
    discoverer = FakeDiscoverer(["https://example.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "ShouldNotBeUsed"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = None
    sink.load_latest_schema.return_value = {"name": "CachedSchema", "baseSelector": "div.item"}
    sink.start_run.return_value = 1
    sink.save_run.return_value = 1

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([_complete_record(quartos=5)], []),
        sink=sink,
        source_name="imob-test",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url=None,
        regenerate_schema=False,
    )

    assert result.normalized == [
        {**_complete_record(quartos=5), "_quality": {"valid": True, "warnings": []}}
    ]
    sink.load_latest_schema.assert_called_once_with("imob-test")
    # o schema_generator.generate não foi chamado
    assert schema_generator.sample_url is None


@pytest.mark.anyio
async def test_pipeline_regenerate_schema_ignores_cache(config, output):
    """Com regenerate_schema=True, o cache é ignorado e o schema generator é chamado."""
    discoverer = FakeDiscoverer(["https://example.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "FreshSchema"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = None
    sink.load_latest_schema.return_value = {"name": "CachedSchema"}
    sink.start_run.return_value = 1
    sink.save_run.return_value = 1

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([_complete_record(quartos=6)], []),
        sink=sink,
        source_name="imob-test",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/fresh",
        regenerate_schema=True,
    )

    assert result.normalized == [
        {**_complete_record(quartos=6), "_quality": {"valid": True, "warnings": []}}
    ]
    # load_latest_schema NÃO foi chamado
    sink.load_latest_schema.assert_not_called()
    assert schema_generator.sample_url == "https://example.com/imovel/fresh"


@pytest.mark.anyio
async def test_pipeline_errors_without_sample_url_and_no_cached_schema(config, output):
    """Sem sample_url e sem schema cacheado, o pipeline deve lançar ValueError."""
    discoverer = FakeDiscoverer(["https://example.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "Irrelevant"})

    sink = MagicMock()
    sink.load_latest_discovery.return_value = None
    sink.load_latest_schema.return_value = None

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler([], []),
        sink=sink,
        source_name="imob-test",
    )

    with pytest.raises(ValueError, match="sample_url"):
        await pipeline.run(
            "https://example.com",
            sample_url=None,
        )


@pytest.mark.anyio
async def test_pipeline_exterminator_rejects_incomplete_records(config, output):
    """Registros sem campos obrigatórios são rejeitados antes da normalização."""
    discoverer = FakeDiscoverer(["https://example.com/imovel/1"])
    schema_generator = FakeSchemaGenerator({"name": "Imovel"})

    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=discoverer,
        schema_generator=schema_generator,
        crawler_factory=lambda schema: FakeCrawler(
            data=[
                _complete_record(quartos=3),
                {"quartos": 2},  # incompleto
                _complete_record(quartos=4, imagem=""),  # imagem vazia
            ],
            errors=[],
        ),
        source_name="example",
    )

    result = await pipeline.run(
        "https://example.com",
        sample_url="https://example.com/imovel/1",
    )

    assert len(result.normalized) == 1
    assert len(result.rejected) == 2
    assert result.rejected[0].missing_fields == ["bairro", "cidade", "valor", "tipo_imovel", "url", "imagem"]
    assert result.rejected[1].missing_fields == ["imagem"]

    assert output.rejected.exists()
    rejected_payload = json.loads(output.rejected.read_text())
    assert rejected_payload["metadata"]["count"] == 2

    quality_report = json.loads(output.quality_report.read_text())
    assert quality_report["exterminated_count"] == 2
    assert quality_report["extermination_reasons"] == {
        "bairro": 1,
        "cidade": 1,
        "valor": 1,
        "tipo_imovel": 1,
        "url": 1,
        "imagem": 2,
    }


@pytest.mark.anyio
async def test_pipeline_requires_source_name(config, output):
    """Pipeline deve exigir source_name explicitamente."""
    pipeline = Pipeline(
        config=config,
        output=output,
        discoverer=FakeDiscoverer([]),
        schema_generator=FakeSchemaGenerator({"name": "Imovel"}),
        crawler_factory=lambda schema: FakeCrawler([], []),
    )

    with pytest.raises(ValueError, match="source_name"):
        await pipeline.run("https://example.com")
