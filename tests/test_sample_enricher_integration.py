import pytest

from crawler_machine.prospecting.models import Candidate
from crawler_machine.prospecting.sample_finder import (
    GoogleCustomSearchGateway,
    HttpResponse,
    SampleEnricher,
)


def _api_response(links):
    return {
        "items": [
            {"link": link, "title": f"Imóvel {i}"}
            for i, link in enumerate(links)
        ]
    }


def _candidate(source_name="imob-x", base_url="https://imob-x.com.br"):
    return Candidate(
        city="Jaraguá do Sul",
        state="SC",
        name="Imob X",
        base_url=base_url,
        source_name=source_name,
        phone=None,
        address=None,
        google_place_id="p1",
    )


def test_enricher_finds_apartment_through_full_api_response():
    requester_calls = []

    def requester(url, headers, params):
        requester_calls.append(params["q"])
        # Responde só para a query com cidade/UF do apartamento.
        if '"apartamento" "Jaraguá do Sul" "SC"' in params["q"]:
            return HttpResponse(
                200,
                _api_response(
                    [
                        "https://imob-x.com.br",
                        "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-42",
                    ]
                ),
            )
        return HttpResponse(200, _api_response([]))

    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )
    enricher = SampleEnricher(gateway, sleep=lambda _: None, delay=0.0)

    result = enricher.enrich([_candidate()])

    assert len(result) == 1
    assert result[0].sample_url == "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-42"
    assert "apartamento" in requester_calls[0]


def test_enricher_falls_back_to_house_when_others_are_absent():
    def requester(url, headers, params):
        # Só responde para casa sem cidade.
        if '"casa"' in params["q"] and '"Jaraguá do Sul"' not in params["q"]:
            return HttpResponse(
                200,
                _api_response(
                    ["https://imob-x.com.br/imovel/casa-jaragua-do-sul-7"]
                ),
            )
        return HttpResponse(200, _api_response([]))

    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )
    enricher = SampleEnricher(gateway, sleep=lambda _: None, delay=0.0)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url == "https://imob-x.com.br/imovel/casa-jaragua-do-sul-7"


def test_enricher_emits_null_when_api_returns_no_results():
    def requester(url, headers, params):
        return HttpResponse(200, _api_response([]))

    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )
    enricher = SampleEnricher(gateway, sleep=lambda _: None, delay=0.0)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url is None
