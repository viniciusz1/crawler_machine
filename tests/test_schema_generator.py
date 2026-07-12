from typing import Any

import pytest

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.schema_generator import SchemaGenerator


class FakeSchemaGenerator:
    def __init__(self, schema: dict):
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
async def test_schema_generator_builds_prompt_and_returns_schemas(fields, llm_config):
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


def test_schema_generator_builds_query_from_fields(fields, llm_config):
    generator = SchemaGenerator(llm_config=llm_config, fields=fields)

    query = generator._build_query()

    assert "quartos" in query
    assert "valor" in query
    assert "Número de quartos" in query
