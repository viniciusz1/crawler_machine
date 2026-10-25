from dataclasses import FrozenInstanceError

import pytest

from crawler_machine.prospecting.models import (
    Candidate,
    Place,
)


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
    candidate = Candidate(
        city="Joinville",
        state="SC",
        name="Imob Boa",
        base_url="https://imob-boa.com.br",
        source_name="imob-boa-com-br",
    )
    with pytest.raises(FrozenInstanceError):
        candidate.name = "Outra"  # type: ignore[misc]

