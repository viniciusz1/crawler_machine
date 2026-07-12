from __future__ import annotations

from typing import Any

import pytest

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.schema_generator import SchemaGenerator


class FakeSchemaGenerator:
    def __init__(self, schema: dict[str, Any]):
        self.schema = schema
        self.calls: list[tuple[str, str]] = []

    async def generate(self, **kwargs: Any) -> dict:
        self.calls.append((kwargs["url"], kwargs["schema_type"]))
        return self.schema


@pytest.fixture
def fields():
    return [
        FieldConfig(name="quartos", description="Número de quartos", coerce="int"),
        FieldConfig(name="valor", description="Valor do imóvel", coerce="currency"),
    ]


@pytest.fixture
def llm_config():
    return LLMConfig(
        provider="deepseek/deepseek-v4-pro",
        base_url="https://api.deepseek.com",
        api_key_env="DEEPSEEK_API_KEY",
    )


@pytest.mark.anyio
async def test_schema_generator_generates_xpath_and_css(fields, llm_config):
    expected_schema = {"name": "ImovelDetalhes", "baseSelector": "//body", "fields": []}
    fake = FakeSchemaGenerator(expected_schema)

    generator = SchemaGenerator(
        llm_config=llm_config, fields=fields, generator=fake.generate
    )
    result = await generator.generate("https://example.com/imovel/1")

    assert "metadata" in result
    assert "schemas" in result
    assert result["schemas"]["xpath"] == expected_schema
    assert result["schemas"]["css"] == expected_schema
    assert fake.calls == [
        ("https://example.com/imovel/1", "XPATH"),
        ("https://example.com/imovel/1", "CSS"),
    ]


@pytest.mark.anyio
async def test_schema_generator_merges_distinct_schemas(fields, llm_config):
    async def generate(**kwargs: Any) -> dict:
        return {"name": kwargs["schema_type"], "baseSelector": f"{kwargs['schema_type'].lower()}-selector"}

    generator = SchemaGenerator(
        llm_config=llm_config, fields=fields, generator=generate
    )
    result = await generator.generate("https://example.com/imovel/1")

    assert result["schemas"]["xpath"]["name"] == "XPATH"
    assert result["schemas"]["css"]["name"] == "CSS"


def test_schema_generator_default_schema_type_is_css_for_single_call(fields, llm_config):
    generator = SchemaGenerator(llm_config=llm_config, fields=fields)
    assert generator._schema_type == "CSS"
