import json
from pathlib import Path

from typer.testing import CliRunner

from crawler_machine.cli import app

runner = CliRunner()


def test_discover_help_shows_save_to_db_option():
    """Verifica que --save-to-db e --source-name aparecem na ajuda do discover."""
    result = runner.invoke(app, ["discover", "--help"])
    assert result.exit_code == 0
    assert "--save-to-db" in result.output
    assert "--source-name" in result.output


def test_run_help_shows_regenerate_flags():
    """Verifica que --regenerate-discovery e --regenerate-schema aparecem na ajuda do run."""
    result = runner.invoke(app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--regenerate-discovery" in result.output
    assert "--regenerate-schema" in result.output
    assert "--enable-llm-fallback" in result.output


def test_crawl_help_shows_enable_llm_fallback():
    """Verifica que --enable-llm-fallback aparece na ajuda do crawl."""
    result = runner.invoke(app, ["crawl", "--help"])
    assert result.exit_code == 0
    assert "--enable-llm-fallback" in result.output


def test_run_requires_source_name():
    """--source-name deve ser obrigatório no comando run."""
    result = runner.invoke(app, ["run", "https://example.com"])
    assert result.exit_code != 0
    assert "--source-name" in result.output or "source-name" in result.output


def test_discover_requires_source_name():
    """--source-name deve ser obrigatório no comando discover."""
    result = runner.invoke(app, ["discover", "https://example.com"])
    assert result.exit_code != 0
    assert "--source-name" in result.output or "source-name" in result.output


def test_schema_requires_source_name():
    """--source-name deve ser obrigatório no comando schema."""
    result = runner.invoke(app, ["schema", "https://example.com/imovel/1"])
    assert result.exit_code != 0
    assert "--source-name" in result.output or "source-name" in result.output


def test_schema_help_shows_save_to_db_option():
    """Verifica que --save-to-db e --source-name aparecem na ajuda do schema."""
    result = runner.invoke(app, ["schema", "--help"])
    assert result.exit_code == 0
    assert "--save-to-db" in result.output
    assert "--source-name" in result.output


def test_normalize_command(tmp_path: Path):
    raw_file = tmp_path / "raw.json"
    raw_file.write_text(
        json.dumps(
            {
                "metadata": {"count": 2},
                "data": [
                    {
                        "bairro": "Centro",
                        "cidade": "Jaraguá do Sul",
                        "tipo_imovel": "Apartamento",
                        "url": "https://example.com/imovel/1",
                        "imagem": "https://example.com/imovel/1.jpg",
                        "quartos": "3 (sendo 1 suíte)",
                        "valor": "R$ 450.000,00",
                    },
                    {
                        "bairro": "Centro",
                        "cidade": "Jaraguá do Sul",
                        "tipo_imovel": "Casa",
                        "url": "https://example.com/imovel/2",
                        "imagem": "",
                        "quartos": "2",
                        "valor": "R$ 200.000,00",
                    },
                ],
            }
        )
    )

    config_file = tmp_path / "domain.json"
    config_file.write_text(
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
                    {"name": "quartos", "description": "Número de quartos", "coerce": "int"},
                    {"name": "valor", "description": "Valor do imóvel", "coerce": "currency"},
                ],
            }
        )
    )

    result = runner.invoke(
        app,
        [
            "normalize",
            str(raw_file),
            "--config",
            str(config_file),
            "--output",
            str(tmp_path / "output"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "1 registros normalizados | 1 eliminados" in result.output
