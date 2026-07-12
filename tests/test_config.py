import json
from pathlib import Path

import pytest

from crawler_machine.config import ConfigLoader, DomainConfig, FieldConfig


@pytest.fixture
def sample_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "domain.json"
    config_path.write_text(
        json.dumps(
            {
                "llm": {
                    "provider": "deepseek/deepseek-v4-pro",
                    "base_url": "https://api.deepseek.com",
                    "api_key_env": "DEEPSEEK_API_KEY",
                },
                "crawler": {
                    "page_timeout": 30000,
                    "max_concurrent": 5,
                    "chunk_size": 50,
                    "chunk_delay": 2.0,
                    "headless": True,
                },
                "discovery": {"max_urls": 500},
                "fields": [
                    {
                        "name": "quartos",
                        "description": "Número de quartos",
                        "coerce": "int",
                    },
                    {
                        "name": "valor",
                        "description": "Valor do imóvel",
                        "coerce": "currency",
                    },
                ],
            }
        )
    )
    return config_path


def test_load_config(sample_config: Path):
    config = ConfigLoader.load(sample_config)

    assert isinstance(config, DomainConfig)
    assert config.llm.provider == "deepseek/deepseek-v4-pro"
    assert config.llm.base_url == "https://api.deepseek.com"
    assert config.llm.api_key_env == "DEEPSEEK_API_KEY"
    assert config.crawler.page_timeout == 30000
    assert config.crawler.max_concurrent == 5
    assert config.discovery.max_urls == 500
    assert len(config.fields) == 2
    assert config.fields[0] == FieldConfig(
        name="quartos", description="Número de quartos", coerce="int"
    )
