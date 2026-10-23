from __future__ import annotations

from unittest.mock import patch

from crawler_machine.sink import PostgresConfig, build_source_name


def test_build_source_name_from_url():
    assert build_source_name("https://imbsmart.com.br") == "imbsmart-com-br"


def test_build_source_name_from_explicit_name():
    assert build_source_name("https://example.com", "Imobiliária Modelo") == "imobiliaria-modelo"


def test_postgres_config_from_env_requires_all_fields():
    with patch.dict("os.environ", {"DB_HOST": "localhost"}, clear=True):
        assert PostgresConfig.from_env() is None

    env = {
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_DATABASE": "imob",
        "DB_USERNAME": "user",
        "DB_PASSWORD": "pass",
    }
    with patch.dict("os.environ", env, clear=True):
        config = PostgresConfig.from_env()
        assert config == PostgresConfig(
            host="localhost",
            port=5432,
            database="imob",
            user="user",
            password="pass",
        )
