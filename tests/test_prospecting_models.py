from dataclasses import FrozenInstanceError

import pytest

from crawler_machine.prospecting.models import (
    Candidate,
    CityTarget,
    Place,
    ProspectingResult,
    Summary,
)


def test_city_target_label_joins_name_and_state():
    city = CityTarget(name="Joinville", state="SC")
    assert city.label == "Joinville, SC"


def test_place_defaults_source_to_google_places():
    place = Place(
        place_id="abc",
        name="Imob Teste",
        website="https://imob-teste.com.br",
        phone=None,
        address="Rua X",
        city="Joinville",
        state="SC",
    )
    assert place.source == "google_places"


def test_candidate_defaults_to_candidate_status():
    candidate = Candidate(
        city="Joinville",
        state="SC",
        name="Imob Teste",
        base_url="https://imob-teste.com.br",
        source_name="imob-teste-com-br",
    )
    assert candidate.status == "candidate"
    assert candidate.reject_reason is None
    assert candidate.sample_url is None


def test_candidate_to_dict_contains_all_fields():
    candidate = Candidate(
        city="Joinville",
        state="SC",
        name="Imob Teste",
        base_url="https://imob-teste.com.br",
        source_name="imob-teste-com-br",
        google_place_id="abc",
    )
    data = candidate.to_dict()
    assert data["city"] == "Joinville"
    assert data["state"] == "SC"
    assert data["base_url"] == "https://imob-teste.com.br"
    assert data["source_name"] == "imob-teste-com-br"
    assert data["status"] == "candidate"
    assert data["google_place_id"] == "abc"


def test_models_are_frozen():
    city = CityTarget(name="Joinville", state="SC")
    with pytest.raises(FrozenInstanceError):
        city.name = "Blumenau"  # type: ignore[misc]


def test_prospecting_result_partitions_accepted_and_rejected():
    accepted = Candidate(
        city="Joinville",
        state="SC",
        name="Imob Boa",
        base_url="https://imob-boa.com.br",
        source_name="imob-boa-com-br",
        status="candidate",
    )
    rejected = Candidate(
        city="Joinville",
        state="SC",
        name="ZAP",
        base_url="https://zapimoveis.com.br",
        source_name="zapimoveis-com-br",
        status="rejected",
        reject_reason="aggregator",
    )
    result = ProspectingResult(
        query_cities=["Joinville, SC"],
        candidates=[accepted, rejected],
        summary=Summary(total=2, candidates=1, rejected=1),
    )

    assert result.accepted == [accepted]
    assert result.rejected == [rejected]
    assert result.summary.total == 2
    assert result.summary.candidates == 1
    assert result.summary.rejected == 1
