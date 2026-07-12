import pytest

from crawler_machine.prospecting.models import Candidate, CityTarget, Place
from crawler_machine.prospecting.places import PlacesGateway
from crawler_machine.prospecting.prospector import Prospector
from crawler_machine.prospecting.repository import InMemoryProspectRepository


class FakePlacesGateway(PlacesGateway):
    def __init__(self, by_city: dict[str, list[Place]]):
        self._by_city = by_city
        self.calls: list[tuple[str, str, int]] = []

    def search_imobiliarias(self, city, state, max_results):
        self.calls.append((city, state, max_results))
        return self._by_city.get(f"{city}|{state}", [])[:max_results]


def _place(city, state, name, website, place_id):
    return Place(
        place_id=place_id,
        name=name,
        website=website,
        phone=None,
        address=None,
        city=city,
        state=state,
    )


def test_prospector_classifies_and_dedups_single_city():
    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob Boa", "https://imob-boa.com.br", "1"),
                _place("Joinville", "SC", "ZAP", "https://zapimoveis.com.br", "2"),
                _place("Joinville", "SC", "Sem Site", None, "3"),
                _place("Joinville", "SC", "Imob Boa Filial", "https://imob-boa.com.br", "4"),
            ]
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC")], gateway, max_per_city=30
    )

    result = prospector.run()

    assert result.summary.total == 4
    assert result.summary.candidates == 1
    assert result.summary.rejected == 3

    accepted = result.accepted
    assert len(accepted) == 1
    assert accepted[0].name == "Imob Boa"
    assert accepted[0].source_name == "imob-boa-com-br"

    reasons = {c.reject_reason for c in result.rejected}
    assert reasons == {"aggregator", "no_website", "duplicate_domain"}


def test_prospector_dedup_across_cities():
    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob X", "https://imob-x.com.br", "1"),
            ],
            "Blumenau|SC": [
                _place("Blumenau", "SC", "Imob X", "https://imob-x.com.br", "2"),
            ],
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")],
        gateway,
    )

    result = prospector.run()

    assert result.summary.total == 2
    assert result.summary.candidates == 1
    assert result.summary.rejected == 1

    duplicate = result.rejected[0]
    assert duplicate.reject_reason == "duplicate_domain"
    assert duplicate.city == "Blumenau"


def test_prospector_empty_city_yields_empty_result():
    gateway = FakePlacesGateway({})
    prospector = Prospector([CityTarget("Joinville", "SC")], gateway)

    result = prospector.run()

    assert result.summary.total == 0
    assert result.summary.candidates == 0
    assert result.summary.rejected == 0
    assert result.candidates == []


def test_prospector_query_cities_use_labels():
    gateway = FakePlacesGateway({})
    prospector = Prospector(
        [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")], gateway
    )

    result = prospector.run()

    assert result.query_cities == ["Joinville, SC", "Blumenau, SC"]


def test_prospector_passes_max_per_city_to_gateway():
    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", f"Imob {i}", f"https://imob-{i}.com.br", str(i))
                for i in range(50)
            ]
        }
    )
    prospector = Prospector([CityTarget("Joinville", "SC")], gateway, max_per_city=10)

    result = prospector.run()

    assert gateway.calls[0] == ("Joinville", "SC", 10)
    assert result.summary.total == 10
    assert result.summary.candidates == 10


def test_prospector_gateway_failure_propagates():
    class ExplodingGateway(PlacesGateway):
        def search_imobiliarias(self, city, state, max_results):
            raise RuntimeError("boom")

    prospector = Prospector(
        [CityTarget("Joinville", "SC")], ExplodingGateway()
    )

    with pytest.raises(RuntimeError, match="boom"):
        prospector.run()


def _candidate_for(name, base_url, city="Joinville", state="SC", status="candidate"):
    return Candidate(
        city=city,
        state=state,
        name=name,
        base_url=base_url,
        source_name="imob-velha-com-br" if base_url else None,
        status=status,
        reject_reason=None if status == "candidate" else "aggregator",
        google_place_id="old",
    )


def test_prospector_filters_already_stored_domains():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [_candidate_for("Imob Velha", "https://imob-velha.com.br")],
        "run-1",
    )

    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob Velha", "https://imob-velha.com.br", "1"),
                _place("Joinville", "SC", "Imob Nova", "https://imob-nova.com.br", "2"),
            ]
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC")],
        gateway,
        repository=repo,
        run_id="run-2",
    )

    result = prospector.run()

    assert result.summary.total == 1
    assert result.accepted[0].name == "Imob Nova"


def test_prospector_force_includes_already_stored_domains():
    repo = InMemoryProspectRepository()
    repo.save_candidates(
        [_candidate_for("Imob Velha", "https://imob-velha.com.br")],
        "run-1",
    )

    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob Velha", "https://imob-velha.com.br", "1"),
                _place("Joinville", "SC", "Imob Nova", "https://imob-nova.com.br", "2"),
            ]
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC")],
        gateway,
        repository=repo,
        run_id="run-2",
        force=True,
    )

    result = prospector.run()

    assert result.summary.total == 2


def test_prospector_saves_candidates_city_by_city():
    repo = InMemoryProspectRepository()
    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob A", "https://imob-a.com.br", "1"),
            ],
            "Blumenau|SC": [
                _place("Blumenau", "SC", "Imob B", "https://imob-b.com.br", "2"),
            ],
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")],
        gateway,
        repository=repo,
        run_id="run-1",
    )

    prospector.run()

    assert repo.count() == 2


def test_prospector_continues_on_save_failure():
    class FailingRepository(InMemoryProspectRepository):
        def save_candidates(self, candidates, run_id):
            if any(c.city == "Blumenau" for c in candidates):
                raise RuntimeError("banco indisponível")
            super().save_candidates(candidates, run_id)

    repo = FailingRepository()
    gateway = FakePlacesGateway(
        {
            "Joinville|SC": [
                _place("Joinville", "SC", "Imob A", "https://imob-a.com.br", "1"),
            ],
            "Blumenau|SC": [
                _place("Blumenau", "SC", "Imob B", "https://imob-b.com.br", "2"),
            ],
        }
    )
    prospector = Prospector(
        [CityTarget("Joinville", "SC"), CityTarget("Blumenau", "SC")],
        gateway,
        repository=repo,
        run_id="run-1",
    )

    result = prospector.run()

    assert result.summary.total == 2
    assert repo.count() == 1
    assert len(result.save_errors) == 1
    assert "Blumenau" in result.save_errors[0]
