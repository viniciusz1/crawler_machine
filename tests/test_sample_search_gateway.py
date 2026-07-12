import pytest

from crawler_machine.prospecting.sample_finder import (
    GoogleCustomSearchGateway,
    HttpResponse,
    SearchError,
)


def make_fake_requester(responses):
    """Devolve (requester, calls). ``calls`` registra (url,)."""
    calls: list[str] = []
    queue = list(responses)

    def requester(url, headers=None, params=None):
        calls.append((url, headers, params))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    return requester, calls


def _result_raw(link):
    return {"link": link}


def _search_payload(links):
    return {"items": [_result_raw(link) for link in links]}


def test_search_returns_parsed_urls():
    payload = _search_payload(
        [
            "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-1",
            "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-2",
        ]
    )
    requester, _ = make_fake_requester([HttpResponse(200, payload)])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    urls = gateway.search('site:imob-x.com.br "apartamento"')

    assert urls == [
        "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-1",
        "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-2",
    ]


def test_search_sends_correct_params():
    payload = _search_payload([])
    requester, calls = make_fake_requester([HttpResponse(200, payload)])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    gateway.search('site:imob-x.com.br "apartamento"', num_results=5)

    assert len(calls) == 1
    url, headers, params = calls[0]
    assert "https://www.googleapis.com/customsearch/v1" in url
    assert params["key"] == "key"
    assert params["cx"] == "cx"
    assert params["q"] == 'site:imob-x.com.br "apartamento"'
    assert params["num"] == 5


def test_search_limits_to_num_results():
    payload = _search_payload([f"https://imob-x.com.br/imovel/{i}" for i in range(10)])
    requester, _ = make_fake_requester([HttpResponse(200, payload)])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    urls = gateway.search("apartamento", num_results=3)

    assert len(urls) == 3


def test_search_raises_on_client_error():
    payload = {"error": {"message": "API key invalid"}}
    requester, _ = make_fake_requester([HttpResponse(403, payload)])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    with pytest.raises(SearchError, match="403"):
        gateway.search("apartamento")


def test_search_raises_on_rate_limit():
    requester, _ = make_fake_requester([HttpResponse(429, {})])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    with pytest.raises(SearchError, match="429"):
        gateway.search("apartamento")


def test_search_raises_on_server_error():
    requester, _ = make_fake_requester([HttpResponse(500, {})])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    with pytest.raises(SearchError, match="500"):
        gateway.search("apartamento")


def test_search_retries_on_timeout_then_raises():
    requester, calls = make_fake_requester(
        [
            TimeoutError("connection timeout"),
            TimeoutError("connection timeout"),
            TimeoutError("connection timeout"),
        ]
    )
    sleeps: list[float] = []
    gateway = GoogleCustomSearchGateway(
        api_key="key",
        cx="cx",
        requester=requester,
        sleep=lambda d: sleeps.append(d),
    )

    with pytest.raises(SearchError, match="timeout"):
        gateway.search("apartamento")

    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_search_succeeds_after_timeout_retry():
    payload = _search_payload(["https://imob-x.com.br/imovel/1"])
    requester, calls = make_fake_requester(
        [TimeoutError("connection timeout"), HttpResponse(200, payload)]
    )
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    urls = gateway.search("apartamento")

    assert urls == ["https://imob-x.com.br/imovel/1"]
    assert len(calls) == 2


def test_missing_api_key_raises():
    with pytest.raises(SearchError, match="GOOGLE_CUSTOM_SEARCH_KEY"):
        GoogleCustomSearchGateway(api_key="", cx="cx")


def test_missing_cx_raises():
    with pytest.raises(SearchError, match="GOOGLE_CUSTOM_SEARCH_CX"):
        GoogleCustomSearchGateway(api_key="key", cx="")


def test_empty_results_returns_empty_list():
    requester, _ = make_fake_requester([HttpResponse(200, {})])
    gateway = GoogleCustomSearchGateway(
        api_key="key", cx="cx", requester=requester
    )

    urls = gateway.search("apartamento")

    assert urls == []
