import json

import pytest
import yaml

from crawler_machine.prospecting.models import (
    Candidate,
    ProspectingResult,
    Summary,
)
from crawler_machine.prospecting.output import write_candidates


def _result() -> ProspectingResult:
    accepted = Candidate(
        city="Jaraguá do Sul",
        state="SC",
        name="Imob Exemplo",
        base_url="https://imob-exemplo.com.br",
        source_name="imob-exemplo-com-br",
        phone="+55 47 3000-0000",
        address="Rua XV, 123",
        google_place_id="ChIJabc",
    )
    rejected = Candidate(
        city="Jaraguá do Sul",
        state="SC",
        name="ZAP",
        base_url="https://zapimoveis.com.br",
        source_name="zapimoveis-com-br",
        status="rejected",
        reject_reason="aggregator",
    )
    return ProspectingResult(
        query_cities=["Jaraguá do Sul, SC"],
        candidates=[accepted, rejected],
        summary=Summary(total=2, candidates=1, rejected=1),
    )


def test_write_yaml_creates_file_with_all_fields(tmp_path):
    out = tmp_path / "candidatos.yaml"
    path = write_candidates(_result(), out, generated_at="2026-07-11T00:00:00+00:00")

    assert path == out
    data = yaml.safe_load(out.read_text(encoding="utf-8"))

    assert data["generated_at"] == "2026-07-11T00:00:00+00:00"
    assert data["query_cities"] == ["Jaraguá do Sul, SC"]

    accepted = data["candidates"][0]
    assert accepted["city"] == "Jaraguá do Sul"
    assert accepted["base_url"] == "https://imob-exemplo.com.br"
    assert accepted["source_name"] == "imob-exemplo-com-br"
    assert accepted["status"] == "candidate"
    assert accepted["sample_url"] is None
    assert accepted["google_place_id"] == "ChIJabc"

    rejected = data["candidates"][1]
    assert rejected["status"] == "rejected"
    assert rejected["reject_reason"] == "aggregator"

    assert data["summary"] == {"total": 2, "candidates": 1, "rejected": 1}


def test_write_json_creates_file_with_all_fields(tmp_path):
    out = tmp_path / "candidatos.json"
    write_candidates(_result(), out, fmt="json", generated_at="2026-07-11T00:00:00+00:00")

    data = json.loads(out.read_text(encoding="utf-8"))

    assert data["generated_at"] == "2026-07-11T00:00:00+00:00"
    assert data["summary"]["candidates"] == 1
    assert len(data["candidates"]) == 2


def test_write_creates_parent_directories(tmp_path):
    out = tmp_path / "nested" / "dir" / "candidatos.yaml"
    write_candidates(_result(), out, generated_at="ts")

    assert out.exists()


def test_write_yaml_preserves_unicode(tmp_path):
    out = tmp_path / "candidatos.yaml"
    write_candidates(_result(), out, generated_at="ts")

    content = out.read_text(encoding="utf-8")
    assert "Jaraguá do Sul" in content
    assert "rua" not in content.lower().replace("rua xv", "")


def test_write_invalid_format_raises(tmp_path):
    out = tmp_path / "candidatos.xml"
    with pytest.raises(ValueError, match="formato não suportado"):
        write_candidates(_result(), out, fmt="xml")


def test_write_defaults_generated_at_when_not_provided(tmp_path):
    out = tmp_path / "candidatos.yaml"
    write_candidates(_result(), out)

    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert isinstance(data["generated_at"], str)
    assert data["generated_at"]  # não vazio
