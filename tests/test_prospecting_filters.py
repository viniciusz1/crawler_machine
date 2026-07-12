import pytest

from crawler_machine.prospecting.filters import (
    AGGREGATOR_DOMAINS,
    classify,
    dedup_by_domain,
    is_aggregator,
    root_domain,
)
from crawler_machine.prospecting.models import Place


def _place(website: str | None, name: str = "Imob", place_id: str = "pid") -> Place:
    return Place(
        place_id=place_id,
        name=name,
        website=website,
        phone=None,
        address="Rua X",
        city="Joinville",
        state="SC",
    )


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.imob.com.br/imovel/1", "imob.com.br"),
        ("https://imob.com.br", "imob.com.br"),
        ("http://filial.imob.com.br/", "imob.com.br"),
        ("https://imob.net", "imob.net"),
        ("https://sub.dom.imob.net", "imob.net"),
        ("imob.com.br:443/imovel", "imob.com.br"),
        ("https://WWW.Exemplo.COM.br", "exemplo.com.br"),
        ("", ""),
        ("not-a-url", "not-a-url"),
    ],
)
def test_root_domain(url: str, expected: str):
    assert root_domain(url) == expected


def test_is_aggregator_detects_known_marketplaces():
    assert is_aggregator("https://www.zapimoveis.com.br") is True
    assert is_aggregator("https://vivareal.com.br/imovel/x") is True
    assert is_aggregator("https://olx.com.br") is True
    assert is_aggregator("https://facebook.com/imob") is True


def test_is_aggregator_false_for_real_estate_site():
    assert is_aggregator("https://imob-exemplo.com.br") is False
    assert is_aggregator(None) is False
    assert is_aggregator("") is False


def test_classify_valid_website_yields_candidate():
    place = _place("https://imob-exemplo.com.br")
    candidate = classify(place)

    assert candidate.status == "candidate"
    assert candidate.reject_reason is None
    assert candidate.base_url == "https://imob-exemplo.com.br"
    assert candidate.source_name == "imob-exemplo-com-br"
    assert candidate.google_place_id == "pid"


def test_classify_missing_website_is_rejected():
    place = _place(None)
    candidate = classify(place)

    assert candidate.status == "rejected"
    assert candidate.reject_reason == "no_website"
    assert candidate.base_url is None
    assert candidate.source_name is None


def test_classify_empty_website_is_rejected_as_no_website():
    place = _place("")
    candidate = classify(place)

    assert candidate.status == "rejected"
    assert candidate.reject_reason == "no_website"


def test_classify_aggregator_website_is_rejected():
    place = _place("https://zapimoveis.com.br")
    candidate = classify(place)

    assert candidate.status == "rejected"
    assert candidate.reject_reason == "aggregator"
    assert candidate.base_url == "https://zapimoveis.com.br"


def test_dedup_keeps_first_and_marks_duplicates():
    candidates = [
        classify(_place("https://imob.com.br", place_id="1")),
        classify(_place("https://imob.com.br", place_id="2")),
    ]
    result = dedup_by_domain(candidates)

    assert result[0].status == "candidate"
    assert result[1].status == "rejected"
    assert result[1].reject_reason == "duplicate_domain"


def test_dedup_distinct_domains_all_kept():
    candidates = [
        classify(_place("https://imob-a.com.br", place_id="1")),
        classify(_place("https://imob-b.com.br", place_id="2")),
    ]
    result = dedup_by_domain(candidates)

    assert all(c.status == "candidate" for c in result)
    assert len(result) == 2


def test_dedup_preserves_no_website_candidates():
    candidates = [
        classify(_place(None, place_id="1")),
        classify(_place(None, place_id="2")),
    ]
    result = dedup_by_domain(candidates)

    assert len(result) == 2
    assert all(c.reject_reason == "no_website" for c in result)


def test_dedup_www_and_bare_domain_are_same_root():
    candidates = [
        classify(_place("https://www.imob.com.br", place_id="1")),
        classify(_place("https://imob.com.br", place_id="2")),
    ]
    result = dedup_by_domain(candidates)

    assert result[0].status == "candidate"
    assert result[1].status == "rejected"
    assert result[1].reject_reason == "duplicate_domain"


def test_aggregator_domains_are_frozen():
    with pytest.raises(AttributeError):
        AGGREGATOR_DOMAINS.add("exemplo.com.br")  # type: ignore[attr-defined]
