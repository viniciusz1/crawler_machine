import pytest

from crawler_machine.prospecting.home_sample_finder import HomeSampleFinder
from crawler_machine.prospecting.models import Candidate


def _candidate(base_url="https://imob-x.com.br", source_name="imob-x"):
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



class _FakeResponse:
    def __init__(self, text: str):
        self.status_code = 200
        self.text = text

    def raise_for_status(self) -> None:
        pass


def _requester(html: str):
    calls = []

    def requester(url: str):
        calls.append(url)
        return _FakeResponse(html)

    return requester, calls


def test_finds_property_link_in_home():
    html = """
    <html>
      <body>
        <a href="/">Home</a>
        <a href="/imovel/apartamento-jaragua-do-sul-42">Apartamento</a>
        <a href="/sobre">Sobre</a>
      </body>
    </html>
    """
    requester, calls = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-42"
    assert calls == ["https://imob-x.com.br/"]


def test_skips_home_link():
    html = """
    <html>
      <body>
        <a href="https://imob-x.com.br/">Home</a>
        <a href="/imovel/casa-jaragua-do-sul-7">Casa</a>
      </body>
    </html>
    """
    requester, calls = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/casa-jaragua-do-sul-7"


def test_returns_none_when_no_property_link():
    html = """
    <html>
      <body>
        <a href="/sobre">Sobre</a>
        <a href="/contato">Contato</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url is None


def test_resolves_relative_urls():
    html = """
    <html>
      <body>
        <a href="imovel/geminado-jaragua-do-sul-3">Geminado</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/geminado-jaragua-do-sul-3"


def test_prefers_deeper_url_with_id():
    html = """
    <html>
      <body>
        <a href="/imoveis">Listagem</a>
        <a href="/imovel/apartamento-jaragua-do-sul-42">Apartamento 42</a>
        <a href="/imovel/casa">Casa sem id</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-42"


def test_handles_request_error():
    def requester(url, **kwargs):
        raise ConnectionError("failed")

    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url is None


def test_ignores_external_links():
    html = """
    <html>
      <body>
        <a href="https://facebook.com/imobx">Facebook</a>
        <a href="/imovel/apartamento-1">Apartamento</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/apartamento-1"


def test_filters_listing_pages_and_chooses_individual():
    html = """
    <html>
      <body>
        <a href="/imoveis/apartamento">Listagem apartamentos</a>
        <a href="/imovel/apartamento-jaragua-do-sul-42">Apartamento 42</a>
        <a href="/cadastrar-imovel">Cadastrar</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/apartamento-jaragua-do-sul-42"


def test_filters_form_pages():
    html = """
    <html>
      <body>
        <a href="/encomenda_imovel">Encomenda</a>
        <a href="/imovel/casa-jaragua-do-sul-7">Casa 7</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/casa-jaragua-do-sul-7"


def test_filters_query_string_filters():
    html = """
    <html>
      <body>
        <a href="/imoveis/apartamento?ordem=preco">Ordenação</a>
        <a href="/imovel/geminado-jaragua-do-sul-3">Geminado 3</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/geminado-jaragua-do-sul-3"


def test_filters_dormitorios_filter():
    html = """
    <html>
      <body>
        <a href="/imoveis/apartamento/dormitorios-2-2">Filtro dormitórios</a>
        <a href="/imovel/casa-jaragua-do-sul-7">Casa 7</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imovel/casa-jaragua-do-sul-7"


def test_falls_back_to_middle_url_when_all_are_listings():
    html = """
    <html>
      <body>
        <a href="/imoveis/apartamento">Listagem 1</a>
        <a href="/imoveis/casa">Listagem 2</a>
        <a href="/imoveis/geminado">Listagem 3 (meio)</a>
        <a href="/imoveis/casa-de-condominio">Listagem 4</a>
        <a href="/imoveis/apartamento-luxo">Listagem 5</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url == "https://imob-x.com.br/imoveis/geminado"


def test_returns_none_when_only_home_and_external_links():
    html = """
    <html>
      <body>
        <a href="/">Home</a>
        <a href="https://facebook.com/imobx">Facebook</a>
      </body>
    </html>
    """
    requester, _ = _requester(html)
    finder = HomeSampleFinder(requester=requester)

    url = finder.find(_candidate())

    assert url is None
