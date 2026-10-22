from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from crawler_machine.playwright_discoverer import (
    FakeListingBrowser,
    PlaywrightListingBrowser,
    PlaywrightListingDiscoverer,
)


def test_discovers_all_property_links_across_url_paginated_listing() -> None:
    pages = {
        "https://imob.example.com/imoveis": """
            <html>
              <body>
                <a href="/contato">Contato</a>
                <div class="lista-imoveis">
                  <a href="/imovel/apartamento-centro-101">Ver imóvel 101</a>
                  <a href="/imovel/casa-jardins-102">Ver imóvel 102</a>
                </div>
                <nav class="pagination">
                  <span class="current">1</span>
                  <a href="/imoveis?pagina=2">2</a>
                  <a href="/imoveis?pagina=2" class="next">Próxima</a>
                </nav>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis?pagina=2": """
            <html>
              <body>
                <div class="lista-imoveis">
                  <a href="/imovel/sobrado-vila-nova-103">Ver imóvel 103</a>
                  <a href="/imovel/terreno-industrial-104">Ver imóvel 104</a>
                </div>
                <nav class="pagination">
                  <a href="/imoveis?pagina=1">1</a>
                  <span class="current">2</span>
                  <a href="/imoveis?pagina=3">Próxima &raquo;</a>
                </nav>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis?pagina=3": """
            <html>
              <body>
                <div class="lista-imoveis">
                  <a href="/imovel/cobertura-centro-105">Ver imóvel 105</a>
                </div>
                <nav class="pagination">
                  <a href="/imoveis?pagina=2">Anterior</a>
                  <span class="current">3</span>
                </nav>
              </body>
            </html>
        """,
    }
    browser = FakeListingBrowser(pages)
    discoverer = PlaywrightListingDiscoverer(browser=browser)

    urls = discoverer.discover_sync("https://imob.example.com/imoveis")

    assert urls == [
        "https://imob.example.com/imovel/apartamento-centro-101",
        "https://imob.example.com/imovel/casa-jardins-102",
        "https://imob.example.com/imovel/sobrado-vila-nova-103",
        "https://imob.example.com/imovel/terreno-industrial-104",
        "https://imob.example.com/imovel/cobertura-centro-105",
    ]
    assert browser.visited_urls == [
        "https://imob.example.com/imoveis",
        "https://imob.example.com/imoveis?pagina=2",
        "https://imob.example.com/imoveis?pagina=3",
    ]
    assert browser.scroll_count == 3


def test_discovers_all_property_links_via_load_more_button_until_exhausted() -> None:
    batch_1 = """
        <html>
          <body>
            <div class="cards">
              <a href="/imovel/101">Ver mais</a>
              <a href="/imovel/102">Ver mais</a>
            </div>
            <button class="btn-carregar">Carregar mais imóveis</button>
          </body>
        </html>
    """
    batch_2 = """
        <html>
          <body>
            <div class="cards">
              <a href="/imovel/101">Ver mais</a>
              <a href="/imovel/102">Ver mais</a>
              <a href="/imovel/103">Ver mais</a>
              <a href="/imovel/104">Ver mais</a>
            </div>
            <button class="btn-carregar">Carregar mais imóveis</button>
          </body>
        </html>
    """
    batch_3_final = """
        <html>
          <body>
            <div class="cards">
              <a href="/imovel/101">Ver mais</a>
              <a href="/imovel/102">Ver mais</a>
              <a href="/imovel/103">Ver mais</a>
              <a href="/imovel/104">Ver mais</a>
              <a href="/imovel/105">Ver mais</a>
            </div>
            <button class="btn-carregar" disabled>Carregar mais imóveis</button>
          </body>
        </html>
    """
    clicks = 0

    def handle_click(_url: str, control) -> str | None:
        nonlocal clicks
        assert "carregar mais" in control.text.lower()
        clicks += 1
        return batch_2 if clicks == 1 else batch_3_final

    browser = FakeListingBrowser(
        {"https://imob.example.com/imoveis": batch_1},
        on_click=handle_click,
    )
    discoverer = PlaywrightListingDiscoverer(browser=browser)

    urls = discoverer.discover_sync("https://imob.example.com/imoveis")

    assert urls == [
        "https://imob.example.com/imovel/101",
        "https://imob.example.com/imovel/102",
        "https://imob.example.com/imovel/103",
        "https://imob.example.com/imovel/104",
        "https://imob.example.com/imovel/105",
    ]
    assert clicks == 2
    assert browser.visited_urls == ["https://imob.example.com/imoveis"]


def test_discovers_property_links_via_js_next_page_button() -> None:
    page_1 = """
        <html>
          <body>
            <a href="/imovel/201">Imóvel 201</a>
            <div class="pagination">
              <button class="active">1</button>
              <button aria-label="Próxima">></button>
            </div>
          </body>
        </html>
    """
    page_2 = """
        <html>
          <body>
            <a href="/imovel/202">Imóvel 202</a>
            <div class="pagination">
              <button>1</button>
              <button class="active">2</button>
              <button aria-label="Próxima" disabled>></button>
            </div>
          </body>
        </html>
    """
    browser = FakeListingBrowser(
        {"https://imob.example.com/imoveis": page_1},
        on_click=lambda _url, _ctrl: page_2,
    )
    discoverer = PlaywrightListingDiscoverer(browser=browser)

    urls = discoverer.discover_sync("https://imob.example.com/imoveis")

    assert urls == [
        "https://imob.example.com/imovel/201",
        "https://imob.example.com/imovel/202",
    ]
    assert len(browser.clicked_controls) == 1


def test_navigates_from_homepage_to_listing_page_and_paginates() -> None:
    pages = {
        "https://imob.example.com/": """
            <html>
              <body>
                <header>
                  <a href="/">Home</a>
                  <a href="/imoveis">Ver todos os imóveis</a>
                  <a href="/contato">Contato</a>
                </header>
                <section class="destaques">
                  <a href="/imovel/destaque-1">Destaque 1</a>
                </section>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis": """
            <html>
              <body>
                <a href="/imovel/destaque-1">Destaque 1</a>
                <a href="/imovel/catalogo-2">Catálogo 2</a>
                <div class="pagination">
                  <a href="/imoveis?page=2" rel="next">Próxima</a>
                </div>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis?page=2": """
            <html>
              <body>
                <a href="/imovel/catalogo-3">Catálogo 3</a>
              </body>
            </html>
        """,
    }
    browser = FakeListingBrowser(pages)
    discoverer = PlaywrightListingDiscoverer(browser=browser)

    urls = discoverer.discover_sync("https://imob.example.com/")

    assert urls == [
        "https://imob.example.com/imovel/destaque-1",
        "https://imob.example.com/imovel/catalogo-2",
        "https://imob.example.com/imovel/catalogo-3",
    ]
    assert browser.visited_urls == [
        "https://imob.example.com/",
        "https://imob.example.com/imoveis",
        "https://imob.example.com/imoveis?page=2",
    ]


def test_stops_when_next_page_yields_no_new_properties_or_hits_limits() -> None:
    pages = {
        "https://imob.example.com/imoveis": """
            <html>
              <body>
                <a href="/imovel/101">Imóvel 101</a>
                <a href="/imovel/102">Imóvel 102</a>
                <a href="/imoveis?pagina=2" rel="next">Próxima</a>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis?pagina=2": """
            <html>
              <body>
                <a href="/imovel/101">Imóvel 101</a>
                <a href="/imovel/102">Imóvel 102</a>
                <a href="/imoveis?pagina=3" rel="next">Próxima</a>
              </body>
            </html>
        """,
        "https://imob.example.com/imoveis?pagina=3": """
            <html>
              <body>
                <a href="/imovel/999">Nunca deve chegar aqui</a>
              </body>
            </html>
        """,
    }
    browser = FakeListingBrowser(pages)
    discoverer = PlaywrightListingDiscoverer(browser=browser)

    urls = discoverer.discover_sync("https://imob.example.com/imoveis")

    assert urls == [
        "https://imob.example.com/imovel/101",
        "https://imob.example.com/imovel/102",
    ]
    assert "https://imob.example.com/imoveis?pagina=3" not in browser.visited_urls


def test_real_playwright_browser_discovers_links_with_load_more_and_url_pagination() -> None:
    pages = {
        "/": """
            <!doctype html>
            <html>
              <body>
                <a href="/imoveis">Ver todos os imóveis</a>
              </body>
            </html>
        """,
        "/imoveis": """
            <!doctype html>
            <html>
              <body>
                <div id="list">
                  <a href="/imovel/apartamento-centro-101">Imóvel 101</a>
                </div>
                <button id="load-more" onclick="
                  const a = document.createElement('a');
                  a.href = '/imovel/casa-jardim-102';
                  a.textContent = 'Imóvel 102';
                  document.getElementById('list').appendChild(a);
                  this.remove();
                  const nav = document.createElement('nav');
                  nav.className = 'pagination';
                  nav.innerHTML = '<a href=\\'/imoveis?pagina=2\\' rel=\\'next\\'>Próxima</a>';
                  document.body.appendChild(nav);
                ">Carregar mais</button>
              </body>
            </html>
        """,
        "/imoveis?pagina=2": """
            <!doctype html>
            <html>
              <body>
                <div id="list">
                  <a href="/imovel/sobrado-vila-103">Imóvel 103</a>
                </div>
              </body>
            </html>
        """,
    }

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            body = pages.get(self.path, "<html><body>Not found</body></html>").encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        base_url = f"http://127.0.0.1:{port}/"
        browser = PlaywrightListingBrowser(
            headless=True,
            page_timeout_ms=10000,
            scroll_pause_ms=50,
            max_scroll_steps=3,
        )
        discoverer = PlaywrightListingDiscoverer(browser=browser)
        urls = discoverer.discover_sync(base_url)

        assert urls == [
            f"http://127.0.0.1:{port}/imovel/apartamento-centro-101",
            f"http://127.0.0.1:{port}/imovel/casa-jardim-102",
            f"http://127.0.0.1:{port}/imovel/sobrado-vila-103",
        ]
    finally:
        server.shutdown()
        server.server_close()


