from crawler_machine.prospecting.models import Candidate, Place
from crawler_machine.prospecting.repository import InMemoryProspectRepository


def _place(name: str, website: str | None, place_id: str = "p1") -> Place:
    return Place(
        place_id=place_id,
        name=name,
        website=website,
        phone=None,
        address=None,
        city="Joinville",
        state="SC",
    )


def _candidate(
    name: str, base_url: str | None, status: str = "candidate"
) -> Candidate:
    return Candidate(
        city="Joinville",
        state="SC",
        name=name,
        base_url=base_url,
        source_name="imob-boa-com-br" if base_url else None,
        status=status,
        reject_reason=None if status == "candidate" else "aggregator",
        google_place_id="p1",
    )


def test_filter_new_places_removes_already_stored_domains():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [_candidate("Imob Boa", "https://imob-boa.com.br")], "run-1"
    )

    places = [
        _place("Imob Boa", "https://imob-boa.com.br"),
        _place("Imob Nova", "https://imob-nova.com.br"),
    ]
    result = repo.filter_new_places(places)

    assert len(result) == 1
    assert result[0].name == "Imob Nova"


def test_filter_new_places_force_includes_all_domains():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [_candidate("Imob Boa", "https://imob-boa.com.br")], "run-1"
    )

    places = [
        _place("Imob Boa", "https://imob-boa.com.br"),
        _place("Imob Nova", "https://imob-nova.com.br"),
    ]
    result = repo.filter_new_places(places, force=True)

    assert len(result) == 2


def test_save_candidates_stores_rejected_too():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [
            _candidate("Imob Boa", "https://imob-boa.com.br", "candidate"),
            _candidate("ZAP", "https://zapimoveis.com.br", "rejected"),
        ],
        "run-1",
    )

    assert repo.count() == 2
    assert repo.get("imob-boa.com.br") is not None
    assert repo.get("zapimoveis.com.br") is not None


def test_save_candidates_upserts_existing_domain():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [_candidate("Old Name", "https://imob-boa.com.br")], "run-1"
    )

    repo.save_candidates(
        [_candidate("New Name", "https://imob-boa.com.br")], "run-2"
    )

    assert repo.count() == 1
    stored = repo.get("imob-boa.com.br")
    assert stored is not None
    assert stored["run_id"] == "run-2"
    assert stored["candidate"].name == "New Name"


def test_filter_new_places_skips_places_without_website():
    repo = InMemoryProspectRepository()
    places = [
        _place("Sem Site", None),
        _place("Imob Nova", "https://imob-nova.com.br"),
    ]

    result = repo.filter_new_places(places)

    assert len(result) == 2
    assert result[0].name == "Sem Site"
