from unittest.mock import MagicMock

import yaml
from typer.testing import CliRunner

from crawler_machine.cli import app

runner = CliRunner()


def _prospecting_yaml(candidates):
    return {
        "generated_at": "2025-01-01T00:00:00+00:00",
        "query_cities": ["Jaraguá do Sul, SC"],
        "candidates": candidates,
        "summary": {"total": len(candidates), "candidates": 0, "rejected": 0},
    }


def _candidate(source_name="imob-x", base_url="https://imob-x.com.br", status="candidate"):
    return {
        "city": "Jaraguá do Sul",
        "state": "SC",
        "name": "Imob X",
        "base_url": base_url,
        "source_name": source_name,
        "phone": None,
        "address": None,
        "google_place_id": "p1",
        "source": "google_places",
        "status": status,
        "reject_reason": None,
    }


def test_enrich_samples_home_help_shows_command():
    result = runner.invoke(
        app, ["prospecting", "enrich-samples-home", "--help"]
    )

    assert result.exit_code == 0
    assert "enrich-samples-home" in result.output
    assert "--dry-run" in result.output


def test_enrich_samples_home_generates_enriched_yaml(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    input_file = tmp_path / "candidates.yaml"
    input_file.write_text(yaml.safe_dump(_prospecting_yaml([_candidate()])))

    fake_enricher = MagicMock()
    fake_enricher.enrich.return_value = [
        MagicMock(
            base_url="https://imob-x.com.br",
            source_name="imob-x",
            sample_url="https://imob-x.com.br/imovel/apartamento-1",
        )
    ]
    monkeypatch.setattr(
        "crawler_machine.cli.commands.prospecting.HomeSampleEnricher",
        lambda *args, **kwargs: fake_enricher,
    )

    result = runner.invoke(
        app, ["prospecting", "enrich-samples-home", str(input_file)]
    )

    assert result.exit_code == 0
    output_file = tmp_path / "candidates.enriched.yaml"
    assert output_file.exists()
    enriched = yaml.safe_load(output_file.read_text())
    assert enriched[0]["sample_url"] == "https://imob-x.com.br/imovel/apartamento-1"


def test_enrich_samples_home_dry_run_does_not_write_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    input_file = tmp_path / "candidates.yaml"
    input_file.write_text(yaml.safe_dump(_prospecting_yaml([_candidate()])))

    result = runner.invoke(
        app, ["prospecting", "enrich-samples-home", str(input_file), "--dry-run"]
    )

    assert result.exit_code == 0
    assert "https://imob-x.com.br/" in result.output
    assert not (tmp_path / "candidates.enriched.yaml").exists()


def test_enrich_samples_home_skips_rejected_candidates(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    input_file = tmp_path / "candidates.yaml"
    input_file.write_text(
        yaml.safe_dump(
            _prospecting_yaml(
                [_candidate(status="candidate"), _candidate(source_name="rejected", status="rejected")]
            )
        )
    )

    fake_enricher = MagicMock()
    fake_enricher.enrich.return_value = [
        MagicMock(
            base_url="https://imob-x.com.br",
            source_name="imob-x",
            sample_url="https://imob-x.com.br/imovel/apartamento-1",
        )
    ]
    monkeypatch.setattr(
        "crawler_machine.cli.commands.prospecting.HomeSampleEnricher",
        lambda *args, **kwargs: fake_enricher,
    )

    runner.invoke(app, ["prospecting", "enrich-samples-home", str(input_file)])

    enriched = yaml.safe_load((tmp_path / "candidates.enriched.yaml").read_text())
    assert len(enriched) == 1
    assert enriched[0]["source_name"] == "imob-x"
