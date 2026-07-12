import pytest

from crawler_machine.prospecting.places import (
    GooglePlacesGateway,
    HttpResponse,
    PlacesError,
)


def make_fake_requester(responses):
    """Devolve (requester, calls). ``calls`` registra (url, headers, body)."""
    calls: list[tuple[str, dict, dict]] = []
    queue = list(responses)

    def requester(url, headers, body):
        calls.append((url, headers, body))
        return queue.pop(0)

    return requester, calls


def _place_raw(place_id, name="Imob", website=None, phone=None, address="Rua X"):
    return {
        "id": place_id,
        "displayName": {"text": name, "languageCode": "pt-BR"},
        "websiteUri": website,
        "formattedAddress": address,
        "internationalPhoneNumber": phone,
    }


def test_search_returns_parsed_places():
    payload = {
        "places": [
            _place_raw("p1", "Imob Alfa", "https://imob-alfa.com.br", "+55 47 1"),
            _place_raw("p2", "Imob Beta", None),
        ]
    }
    requester, _ = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    places = gateway.search_imobiliarias("Joinville", "SC", 30)

    assert len(places) == 2
    assert places[0].place_id == "p1"
    assert places[0].name == "Imob Alfa"
    assert places[0].website == "https://imob-alfa.com.br"
    assert places[0].phone == "+55 47 1"
    assert places[0].city == "Joinville"
    assert places[0].state == "SC"
    assert places[1].website is None


def test_search_respects_max_results():
    payload = {
        "places": [
            _place_raw("p1", "Imob 1", "https://imob-1.com.br"),
            _place_raw("p2", "Imob 2", "https://imob-2.com.br"),
            _place_raw("p3", "Imob 3", "https://imob-3.com.br"),
        ]
    }
    requester, calls = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    places = gateway.search_imobiliarias("Joinville", "SC", 2)

    assert len(places) == 2
    assert len(calls) == 1


def test_search_query_uses_city_and_state():
    payload = {"places": []}
    requester, calls = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    gateway.search_imobiliarias("Jaraguá do Sul", "SC", 10)

    _, headers, body = calls[0]
    assert body["textQuery"] == "imobiliária em Jaraguá do Sul SC"
    assert body["languageCode"] == "pt-BR"
    assert "pageToken" not in body


def test_field_mask_requests_website_uri():
    payload = {"places": []}
    requester, calls = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    gateway.search_imobiliarias("Joinville", "SC", 10)

    _, headers, _ = calls[0]
    assert headers["X-Goog-Api-Key"] == "key"
    assert "places.websiteUri" in headers["X-Goog-FieldMask"]
    assert "places.id" in headers["X-Goog-FieldMask"]
    assert "nextPageToken" in headers["X-Goog-FieldMask"]


def test_search_paginates_via_next_page_token():
    page1 = {
        "places": [_place_raw("p1", "Imob 1", "https://imob-1.com.br")],
        "nextPageToken": "token-abc",
    }
    page2 = {
        "places": [_place_raw("p2", "Imob 2", "https://imob-2.com.br")],
    }
    requester, calls = make_fake_requester(
        [HttpResponse(200, page1), HttpResponse(200, page2)]
    )
    sleeps: list[float] = []
    gateway = GooglePlacesGateway(
        "key", requester=requester, sleep=lambda d: sleeps.append(d), page_delay=2.0
    )

    places = gateway.search_imobiliarias("Joinville", "SC", 30)

    assert [p.place_id for p in places] == ["p1", "p2"]
    assert len(calls) == 2
    _, _, body2 = calls[1]
    assert body2["pageToken"] == "token-abc"
    assert sleeps == [2.0]


def test_search_stops_without_next_page_token():
    payload = {"places": [_place_raw("p1", "Imob 1", "https://imob-1.com.br")]}
    requester, calls = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    places = gateway.search_imobiliarias("Joinville", "SC", 30)

    assert len(places) == 1
    assert len(calls) == 1


def test_search_stops_when_max_reached_mid_pagination():
    page1 = {
        "places": [
            _place_raw("p1", "Imob 1", "https://imob-1.com.br"),
            _place_raw("p2", "Imob 2", "https://imob-2.com.br"),
        ],
        "nextPageToken": "token-abc",
    }
    requester, calls = make_fake_requester([HttpResponse(200, page1)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    places = gateway.search_imobiliarias("Joinville", "SC", 2)

    assert len(places) == 2
    assert len(calls) == 1


def test_search_raises_on_http_error():
    payload = {"error": {"message": "API key invalid"}}
    requester, _ = make_fake_requester([HttpResponse(403, payload)])

    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    with pytest.raises(PlacesError, match="403"):
        gateway.search_imobiliarias("Joinville", "SC", 10)


def test_search_raises_on_server_error():
    requester, _ = make_fake_requester([HttpResponse(500, {})])

    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    with pytest.raises(PlacesError, match="500"):
        gateway.search_imobiliarias("Joinville", "SC", 10)


def test_missing_api_key_raises():
    with pytest.raises(PlacesError, match="GOOGLE_PLACES_API_KEY"):
        GooglePlacesGateway("")


def test_places_without_id_are_skipped():
    payload = {
        "places": [
            {"displayName": {"text": "Sem id"}},
            _place_raw("p1", "Imob 1", "https://imob-1.com.br"),
        ]
    }
    requester, _ = make_fake_requester([HttpResponse(200, payload)])
    gateway = GooglePlacesGateway("key", requester=requester, sleep=lambda _: None)

    places = gateway.search_imobiliarias("Joinville", "SC", 30)

    assert len(places) == 1
    assert places[0].place_id == "p1"
