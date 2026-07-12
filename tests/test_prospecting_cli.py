from unittest.mock import MagicMock

from typer.testing import CliRunner

from crawler_machine.cli import app
from crawler_machine.prospecting.models import Place

runner = CliRunner()


def test_prospecting_find_help_shows_command():
    result = runner.invoke(app, ["prospecting", "find", "--help"])
    assert result.exit_code == 0
    assert "Google Places" in result.output
    assert "--cities" in result.output


def test_prospecting_find_requires_cities_option():
    result = runner.invoke(app, ["prospecting", "find"])
    assert result.exit_code != 0


def test_prospecting_find_rejects_city_without_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")

    result = runner.invoke(app, ["prospecting", "find", "--cities", "Joinville"])

    assert result.exit_code != 0
    assert "malformada" in result.output
    assert "Traceback" not in result.output


def test_prospecting_find_rejects_invalid_state(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")

    result = runner.invoke(
        app, ["prospecting", "find", "--cities", "Joinville,Santa Catarina"]
    )

    assert result.exit_code != 0
    assert "UF inválida" in result.output
    assert "Traceback" not in result.output


def test_prospecting_find_requires_api_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("GOOGLE_PLACES_API_KEY", raising=False)

    result = runner.invoke(app, ["prospecting", "find", "--cities", "Joinville,SC"])

    assert result.exit_code != 0
    assert "GOOGLE_PLACES_API_KEY" in result.output
    assert "Traceback" not in result.output


def test_prospecting_find_rejects_invalid_format(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")

    result = runner.invoke(
        app,
        ["prospecting", "find", "--cities", "Joinville,SC", "--format", "xml"],
    )

    assert result.exit_code != 0
    assert "formato inválido" in result.output
    assert "Traceback" not in result.output


def test_prospecting_find_help_includes_force_flag():
    result = runner.invoke(app, ["prospecting", "find", "--help"])
    assert result.exit_code == 0
    assert "--force" in result.output


def test_prospecting_find_runs_degraded_without_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GOOGLE_PLACES_API_KEY", "fake-key")
    for key in ("DB_HOST", "DB_PORT", "DB_DATABASE", "DB_USERNAME", "DB_PASSWORD"):
        monkeypatch.delenv(key, raising=False)

    fake_place = Place(
        place_id="p1",
        name="Imob Boa",
        website="https://imob-boa.com.br",
        phone=None,
        address=None,
        city="Joinville",
        state="SC",
    )
    fake_gateway = MagicMock()
    fake_gateway.return_value.search_imobiliarias.return_value = [fake_place]

    monkeypatch.setattr(
        "crawler_machine.cli.commands.prospecting.GooglePlacesGateway",
        fake_gateway,
    )

    result = runner.invoke(
        app, ["prospecting", "find", "--cities", "Joinville,SC"]
    )

    assert result.exit_code == 0
    assert "candidato(s)" in result.output
    assert "output/prospecting" in result.output
