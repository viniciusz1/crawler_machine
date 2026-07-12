from __future__ import annotations

import asyncio
import re
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

from crawler_machine.prospecting.models import Candidate


HomeRequester = Callable[[str], "httpx.Response"]


def _render_with_crawl4ai(url: str) -> str:
    """Renderiza a página com Crawl4AI (headless browser) e retorna o HTML."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    browser_config = BrowserConfig(headless=True)
    run_config = CrawlerRunConfig(
        page_timeout=60000,
        js_code="""
            window.scrollTo(0, document.body.scrollHeight);
            await new Promise(r => setTimeout(r, 3000));
        """,
    )

    async def _run() -> str:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url, config=run_config)
            return result.html if result.success else ""

    try:
        return asyncio.run(_run())
    except RuntimeError:
        # Se já houver um event loop rodando (ex: ambiente async), tenta
        # executar de forma compatível.
        loop = asyncio.get_event_loop()
        if loop.is_running():
            return ""
        return loop.run_until_complete(_run())


class HomeSampleFinder:
    """Descobre uma URL de imóvel fazendo scraping da página inicial.

    Extrai todos os links da home, resolve URLs relativas, filtra as que
    pertencem ao mesmo domínio e parecem páginas de imóvel individual
    (presença de ``imovel``, ``apartamento``, ``casa`` ou ``geminado`` no
    path). A home propriamente dita é descartada.

    Quando o scraping estático não encontra nada, o finder pode fazer um
    fallback com Crawl4AI para renderizar JavaScript (carrosséis lazy,
    SPAs que hidratam no client, etc.).
    """

    _PROPERTY_PATTERNS = [
        r"imovel",
        r"apartamento",
        r"casa",
        r"geminado",
        r"detalhes_[a-z]+\.php\?imovel=",
    ]
    _LISTING_PATTERNS = [
        r"/imoveis/",
        r"/filtro/",
        r"cadastr",
        r"encomend",
        r"solicite",
        r"anuncie",
        r"/busca",
        r"dormitorios-",
        r"estagio-",
        r"todos-os-",
        r"todas-as-",
        r"\?ordem=",
        r"pagina=",
        r"ordenacao=",
        r"valorminimo=",
        r"valormaximo=",
        r"/imoveis\?",
        r"tipo\[",
        r"imoveis-para-",
        r"cidade=.+tipo=",
        r"tipo=.+cidade=",
        r"/imovel/comprar$",
        r"/imovel/alugar$",
        r"/imovel/vender$",
        r"/imovel/locacao$",
        r"/imovel/venda$",
    ]
    _HREF_RE = re.compile(r'href\s*=\s*["\']?([^"\'\s>]+)', re.IGNORECASE)
    _JSON_LINK_RE = re.compile(r'["\']link["\']\s*:\s*["\']([^"\']+)["\']', re.IGNORECASE)

    def __init__(
        self,
        requester: HomeRequester | None = None,
        enable_js_fallback: bool = True,
    ) -> None:
        self._requester = requester or self._build_default_requester()
        self._enable_js_fallback = enable_js_fallback

    @staticmethod
    def _build_default_requester() -> HomeRequester:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        }
        client = httpx.Client(timeout=30.0, follow_redirects=True, headers=headers)

        def requester(url: str) -> httpx.Response:
            return client.get(url)

        return requester

    def find(self, candidate: Candidate) -> str | None:
        base_url = candidate.base_url
        if not base_url:
            return None

        sample = self._find_from_home(base_url)
        if sample is not None:
            return sample

        if self._enable_js_fallback:
            html = _render_with_crawl4ai(base_url)
            if html:
                return self._find_from_html(html, base_url)

        return None

    def _find_from_home(self, base_url: str) -> str | None:
        home_url = base_url if base_url.endswith("/") else base_url + "/"
        try:
            response = self._requester(home_url)
            response.raise_for_status()
            html = response.text
        except Exception:
            return None

        return self._find_from_html(html, base_url)

    def _find_from_html(self, html: str, base_url: str) -> str | None:
        all_urls = self._extract_urls(html, base_url)
        if not all_urls:
            return None

        candidates = [url for url in all_urls if not self._is_likely_listing_or_form(url)]
        if candidates:
            candidates.sort(key=self._score_url, reverse=True)
            return candidates[0]

        # Fallback: se todas as URLs parecem listagens/formulários, mas alguma
        # delas indica um imóvel individual (path com "imovel" ou ID numérico),
        # assume que a home lista imóveis em destaque e pega a do meio.
        if any(self._has_property_signal(url) for url in all_urls):
            return all_urls[len(all_urls) // 2]

        return None

    @staticmethod
    def _has_property_signal(url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path or "/"
        query = parsed.query or ""
        # "imovel" como segmento próprio do path (ex: /imovel/... ou /imovel),
        # não como substring de formulários (ex: /encomende-seu-imovel).
        if re.search(r"(^|/)imovel(/|$)", path, re.IGNORECASE):
            # Descarta /imovel/comprar, /imovel/alugar, etc., que são listagens.
            if re.search(r"/imovel/(comprar|alugar|vender|locacao|venda)$", path, re.IGNORECASE):
                return False
            return True
        if re.search(r"imovel=\d+", query, re.IGNORECASE):
            return True
        if re.search(r"/\d+(/|$)", path):
            return True
        return False

    def _extract_urls(self, html: str, base_url: str) -> list[str]:
        raw_links = self._HREF_RE.findall(html)
        # Alguns sites (Next.js, SPA) embebem links em JSON dentro do HTML.
        raw_links.extend(self._JSON_LINK_RE.findall(html))
        found: list[str] = []
        base_domain = self._domain(base_url)

        for link in raw_links:
            absolute = urljoin(base_url, link)
            parsed = urlparse(absolute)
            if not parsed.scheme or not parsed.netloc:
                continue
            if self._domain(absolute) != base_domain:
                continue
            path = parsed.path or "/"
            if self._is_home(path, base_url):
                continue
            if self._looks_like_property(path, parsed.query):
                found.append(absolute)

        return found

    @staticmethod
    def _domain(url: str) -> str:
        return urlparse(url).netloc.lower().lstrip("www.")

    @staticmethod
    def _is_home(path: str, base_url: str) -> bool:
        normalized_path = path.rstrip("/")
        base_path = urlparse(base_url).path.rstrip("/")
        return normalized_path == base_path or normalized_path == ""

    def _looks_like_property(self, path: str, query: str = "") -> bool:
        lower_path = path.lower()
        lower_query = query.lower()
        target = f"{lower_path}?{lower_query}" if lower_query else lower_path
        return any(re.search(pattern, target) for pattern in self._PROPERTY_PATTERNS)

    def _is_likely_listing_or_form(self, url: str) -> bool:
        lower = url.lower()
        return any(re.search(pattern, lower) for pattern in self._LISTING_PATTERNS)

    @staticmethod
    def _score_url(url: str) -> int:
        parsed = urlparse(url)
        path = parsed.path or "/"
        query = parsed.query or ""
        score = 0
        # Profundidade do path.
        segments = [s for s in path.split("/") if s]
        score += len(segments) * 10
        # Presença de número no último segmento (provável ID).
        if segments and re.search(r"\d", segments[-1]):
            score += 20
        # Presença de número na query string (ex: ?imovel=1234).
        if re.search(r"=\d+", query):
            score += 15
        # Termos fortes no path.
        for term in ["apartamento", "casa", "geminado"]:
            if term in path.lower():
                score += 5
        return score


from crawler_machine.prospecting.sample_finder import EnrichedCandidate


class HomeSampleEnricher:
    """Enriquece candidatos com ``sample_url`` via scraping da home."""

    def __init__(self, finder: HomeSampleFinder | None = None) -> None:
        self._finder = finder or HomeSampleFinder()

    def enrich(self, candidates: list[Candidate]) -> list[EnrichedCandidate]:
        enriched: list[EnrichedCandidate] = []
        for candidate in candidates:
            sample_url = self._finder.find(candidate)
            enriched.append(
                EnrichedCandidate(
                    base_url=candidate.base_url or "",
                    source_name=candidate.source_name or "",
                    sample_url=sample_url,
                )
            )
        return enriched
