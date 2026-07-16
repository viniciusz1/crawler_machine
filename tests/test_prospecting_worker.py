from crawler_machine.prospecting.models import Place
from crawler_machine.worker.prospecting import ProspectingExecutor


class FakePlacesGateway:
    def search_imobiliarias(self, city: str, state: str, max_results: int):
        assert (city, state, max_results) == ("Joinville", "SC", 30)
        return [
            Place("known", "Known", "https://known.example.com", None, None, city, state),
            Place("new", "New Agency", "https://www.new-agency.com.br/site", "+55 47", "Rua A", city, state),
            Place("no-site", "No Website", None, None, "Rua B", city, state),
            Place("portal", "Portal", "https://zapimoveis.com.br/x", None, None, city, state),
        ]


def test_executor_uses_gateway_and_keeps_rejected_results_while_skipping_known_domains():
    result = ProspectingExecutor(FakePlacesGateway()).run(
        {
            "city": "Joinville",
            "state": "SC",
            "max_results": 30,
            "requery_known_domains": False,
        },
        {"example.com"},
    )

    assert [item["google_place_id"] for item in result] == ["new", "no-site", "portal"]
    assert result[0]["root_domain"] == "new-agency.com.br"
    assert result[0]["automatic_classification"] == "candidate"
    assert result[1]["automatic_reason"] == "no_website"
    assert result[2]["automatic_reason"] == "aggregator"
    assert all("api_key" not in item for item in result)

    requery = ProspectingExecutor(FakePlacesGateway()).run(
        {
            "city": "Joinville",
            "state": "SC",
            "max_results": 30,
            "requery_known_domains": True,
        },
        {"example.com"},
    )
    assert requery[0]["google_place_id"] == "known"
