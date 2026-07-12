import pytest

from crawler_machine.prospecting.models import Candidate
from crawler_machine.prospecting.sample_finder import (
    EnrichedCandidate,
    SampleEnricher,
    SearchGateway,
)


class FakeSearchGateway(SearchGateway):
    """Gateway fake que mapeia query -> lista de URLs."""

    def __init__(self, responses=None, sleep_calls=None):
        self.responses = responses or {}
        self.calls = []
        self._sleep_calls = sleep_calls or []

    def search(self, query: str, num_results: int = 5) -> list[str]:
        self.calls.append((query, num_results))
        return list(self.responses.get(query, []))[:num_results]


def _candidate(
    source_name="imob-x",
    base_url="https://imob-x.com.br",
    city="Jaraguá do Sul",
    state="SC",
):
    return Candidate(
        city=city,
        state=state,
        name="Imob X",
        base_url=base_url,
        source_name=source_name,
        phone=None,
        address=None,
        google_place_id="p1",
    )


def _enricher(gateway, sleep=None, delay=0.0):
    return SampleEnricher(gateway, sleep=sleep or (lambda _: None), delay=delay)


def test_finds_apartment_on_first_query():
    gateway = FakeSearchGateway(
        {
            'site:https://imob-x.com.br "apartamento" "Jaraguá do Sul" "SC"': [
                "https://imob-x.com.br/imovel/apartamento-1"
            ]
        }
    )
    enricher = _enricher(gateway)

    result = enricher.enrich([_candidate()])

    assert len(result) == 1
    assert result[0] == EnrichedCandidate(
        base_url="https://imob-x.com.br",
        source_name="imob-x",
        sample_url="https://imob-x.com.br/imovel/apartamento-1",
    )


def test_falls_back_to_geminado_when_apartamento_empty():
    gateway = FakeSearchGateway(
        {
            'site:https://imob-x.com.br "geminado" "Jaraguá do Sul" "SC"': [
                "https://imob-x.com.br/imovel/geminado-1"
            ]
        }
    )
    enricher = _enricher(gateway)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url == "https://imob-x.com.br/imovel/geminado-1"
    assert any("apartamento" in call[0] for call in gateway.calls)
    assert any("geminado" in call[0] for call in gateway.calls)


def test_falls_back_to_casa_when_others_empty():
    gateway = FakeSearchGateway(
        {
            'site:https://imob-x.com.br "casa" "Jaraguá do Sul" "SC"': [
                "https://imob-x.com.br/imovel/casa-1"
            ]
        }
    )
    enricher = _enricher(gateway)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url == "https://imob-x.com.br/imovel/casa-1"


def test_rejects_home_url_and_takes_next_result():
    gateway = FakeSearchGateway(
        {
            'site:https://imob-x.com.br "apartamento" "Jaraguá do Sul" "SC"': [
                "https://imob-x.com.br",
                "https://imob-x.com.br/imovel/apartamento-1",
            ]
        }
    )
    enricher = _enricher(gateway)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url == "https://imob-x.com.br/imovel/apartamento-1"


def test_emits_null_when_nothing_found():
    gateway = FakeSearchGateway({})
    enricher = _enricher(gateway)

    result = enricher.enrich([_candidate()])

    assert result[0].sample_url is None


def test_rejects_duplicate_source_names():
    gateway = FakeSearchGateway({})
    enricher = _enricher(gateway)

    with pytest.raises(ValueError, match="source_name duplicado"):
        enricher.enrich([_candidate(source_name="imob-x"), _candidate(source_name="imob-x")])


def test_query_variations_follow_fallback_chain():
    gateway = FakeSearchGateway({})
    sleeps = []
    enricher = SampleEnricher(gateway, sleep=lambda d: sleeps.append(d), delay=0.0)

    enricher.enrich([_candidate()])

    expected_prefixes = [
        'site:https://imob-x.com.br "apartamento" "Jaraguá do Sul" "SC"',
        'site:https://imob-x.com.br "apartamento"',
        'site:https://imob-x.com.br "apartamento" "venda"',
        'site:https://imob-x.com.br "geminado" "Jaraguá do Sul" "SC"',
        'site:https://imob-x.com.br "geminado"',
        'site:https://imob-x.com.br "geminado" "venda"',
        'site:https://imob-x.com.br "casa" "Jaraguá do Sul" "SC"',
        'site:https://imob-x.com.br "casa"',
        'site:https://imob-x.com.br "casa" "venda"',
    ]
    actual = [call[0] for call in gateway.calls]
    assert actual == expected_prefixes
