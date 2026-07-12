import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from crawler_machine.batch import run_batch, BatchError
from crawler_machine.cli import app


runner = CliRunner()


def test_empty_yaml_raises_error(tmp_path: Path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("")

    with pytest.raises(BatchError, match="lista de imobiliárias está vazia"):
        run_batch(yaml_file, output_dir=tmp_path / "output")


def test_duplicate_source_name_raises_error(tmp_path: Path):
    yaml_file = tmp_path / "duplicates.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
  sample_url: https://imob1.com.br/imovel/1
- base_url: https://imob2.com.br
  source_name: imob1-com-br
  sample_url: https://imob2.com.br/imovel/1
"""
    )

    with pytest.raises(BatchError, match="source_name duplicado"):
        run_batch(yaml_file, output_dir=tmp_path / "output")


def test_missing_required_field_raises_error(tmp_path: Path):
    yaml_file = tmp_path / "missing.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
- base_url: https://imob2.com.br
  sample_url: https://imob2.com.br/imovel/1
"""
    )

    with pytest.raises(BatchError, match="campo obrigatório ausente"):
        run_batch(yaml_file, output_dir=tmp_path / "output")


def test_single_item_generates_batch_report(tmp_path: Path):
    yaml_file = tmp_path / "batch.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
  sample_url: https://imob1.com.br/imovel/1
"""
    )

    def fake_runner(
        base_url: str, source_name: str, sample_url: str | None
    ) -> dict[str, Any]:
        return {
            "status": "success",
            "normalized_count": 5,
            "error_count": 0,
            "run_id": 42,
            "output_dir": str(tmp_path / "output" / source_name / "20260101_000000"),
        }

    output_dir = tmp_path / "output"
    report = run_batch(yaml_file, output_dir=output_dir, runner=fake_runner)

    assert report["metadata"]["total"] == 1
    assert report["metadata"]["succeeded"] == 1
    assert report["metadata"]["failed"] == 0
    assert len(report["items"]) == 1

    item = report["items"][0]
    assert item["source_name"] == "imob1-com-br"
    assert item["base_url"] == "https://imob1.com.br"
    assert item["sample_url"] == "https://imob1.com.br/imovel/1"
    assert item["status"] == "success"
    assert item["run_id"] == 42
    assert item["normalized_count"] == 5
    assert item["error_count"] == 0
    assert item["error_message"] is None

    report_files = list((output_dir / "batch-reports").glob("*.json"))
    assert len(report_files) == 1
    saved_report = json.loads(report_files[0].read_text(encoding="utf-8"))
    assert saved_report["metadata"]["total"] == 1


def test_two_items_processed_sequentially(tmp_path: Path):
    yaml_file = tmp_path / "batch.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
  sample_url: https://imob1.com.br/imovel/1
- base_url: https://imob2.com.br
  source_name: imob2-com-br
  sample_url: https://imob2.com.br/imovel/1
"""
    )

    calls: list[tuple[str, str, str | None]] = []

    def fake_runner(
        base_url: str, source_name: str, sample_url: str | None
    ) -> dict[str, Any]:
        calls.append((base_url, source_name, sample_url))
        return {
            "status": "success",
            "normalized_count": 1,
            "error_count": 0,
            "run_id": len(calls),
            "output_dir": str(tmp_path / "output" / source_name),
        }

    report = run_batch(yaml_file, output_dir=tmp_path / "output", runner=fake_runner)

    assert len(calls) == 2
    assert calls[0][1] == "imob1-com-br"
    assert calls[1][1] == "imob2-com-br"
    assert report["metadata"]["total"] == 2
    assert report["metadata"]["succeeded"] == 2
    assert report["metadata"]["failed"] == 0
    assert {item["source_name"] for item in report["items"]} == {
        "imob1-com-br",
        "imob2-com-br",
    }


def test_failure_in_one_item_does_not_stop_others(tmp_path: Path):
    yaml_file = tmp_path / "batch.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
  sample_url: https://imob1.com.br/imovel/1
- base_url: https://imob2.com.br
  source_name: imob2-com-br
  sample_url: https://imob2.com.br/imovel/1
"""
    )

    def fake_runner(
        base_url: str, source_name: str, sample_url: str | None
    ) -> dict[str, Any]:
        if source_name == "imob1-com-br":
            raise RuntimeError("falha simulada")
        return {
            "status": "success",
            "normalized_count": 3,
            "error_count": 0,
            "run_id": 99,
            "output_dir": str(tmp_path / "output" / source_name),
        }

    report = run_batch(yaml_file, output_dir=tmp_path / "output", runner=fake_runner)

    assert report["metadata"]["total"] == 2
    assert report["metadata"]["succeeded"] == 1
    assert report["metadata"]["failed"] == 1

    failed_item = next(
        item for item in report["items"] if item["source_name"] == "imob1-com-br"
    )
    assert failed_item["status"] == "failed"
    assert "falha simulada" in failed_item["error_message"]

    success_item = next(
        item for item in report["items"] if item["source_name"] == "imob2-com-br"
    )
    assert success_item["status"] == "success"


def test_all_items_failed_still_generates_report(tmp_path: Path):
    yaml_file = tmp_path / "batch.yaml"
    yaml_file.write_text(
        """
- base_url: https://imob1.com.br
  source_name: imob1-com-br
  sample_url: https://imob1.com.br/imovel/1
- base_url: https://imob2.com.br
  source_name: imob2-com-br
  sample_url: https://imob2.com.br/imovel/1
"""
    )

    def fake_runner(
        base_url: str, source_name: str, sample_url: str | None
    ) -> dict[str, Any]:
        raise RuntimeError("falha total")

    report = run_batch(yaml_file, output_dir=tmp_path / "output", runner=fake_runner)

    assert report["metadata"]["total"] == 2
    assert report["metadata"]["succeeded"] == 0
    assert report["metadata"]["failed"] == 2
    assert all(item["status"] == "failed" for item in report["items"])

    report_files = list((tmp_path / "output" / "batch-reports").glob("*.json"))
    assert len(report_files) == 1


def test_clone_das_sombras_help_shows_command():
    result = runner.invoke(app, ["clone-das-sombras", "--help"])
    assert result.exit_code == 0
    assert "YAML" in result.output


def test_clone_das_sombras_requires_yaml_file():
    result = runner.invoke(app, ["clone-das-sombras", "inexistente.yaml"])
    assert result.exit_code != 0


def test_clone_das_sombras_shows_friendly_error_for_empty_yaml(tmp_path: Path):
    yaml_file = tmp_path / "empty.yaml"
    yaml_file.write_text("")

    result = runner.invoke(app, ["clone-das-sombras", str(yaml_file)])
    assert result.exit_code != 0
    assert "lista de imobiliárias está vazia" in result.output
    assert "Traceback" not in result.output
