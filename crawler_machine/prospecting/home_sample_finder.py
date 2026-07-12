from __future__ import annotations

import re
from typing import Callable
from urllib.parse import urljoin, urlparse

import httpx

from crawler_machine.prospecting.models import Candidate


HomeRequester = Callable[[str], "httpx.Response"]


class HomeSampleFinder:
    """Descobre uma URL de imóvel fazendo scraping da página inicial.

    Extrai todos os links da home, resolve URLs relativas, filtra as que
    pertencem ao mesmo domínio e parecem páginas de imóvel individual
    (presença de ``imovel``, ``apartamento``, ``casa`` ou ``geminado`` no
    path). A home propriamente dita é descartada.
    """

    _PROPERTY_PATTERNS = [
        r"imovel",
        r"apartamento",
        r"casa",
        r"geminado",
    ]
    _LISTING_PATTERNS = [
        r"/imoveis/",
        r"/filtro/",
        r"cadastr",
        r"encomenda",
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
    ]
    _HREF_RE = re.compile(r'href\s*=\s*["\']?([^"\'\s>]+)', re.IGNORECASE)

    def __init__(
        self,
        requester: HomeRequester | None = None,
    ) -> None:
        self._requester = requester or self._build_default_requester()

    @staticmethod
    def _build_default_requester() -> HomeRequester:
        client = httpx.Client(timeout=30.0, follow_redirects=True)

        def requester(url: str) -> httpx.Response:
            return client.get(url)

        return requester

    def find(self, candidate: Candidate) -> str | None:
        base_url = candidate.base_url
        if not base_url:
            return None

        home_url = base_url if base_url.endswith("/") else base_url + "/"
        try:
            response = self._requester(home_url)
            response.raise_for_status()
            html = response.text
        except Exception:
            return None

        all_urls = self._extract_urls(html, base_url)
        if not all_urls:
            return None

        candidates = [url for url in all_urls if not self._is_likely_listing_or_form(url)]
        if candidates:
            candidates.sort(key=self._score_url, reverse=True)
            return candidates[0]

        # Fallback: se todas as URLs parecem listagens/formulários,
        # assume que a home lista imóveis em destaque e pega a do meio.
        return all_urls[len(all_urls) // 2]

    def _extract_urls(self, html: str, base_url: str) -> list[str]:
        raw_links = self._HREF_RE.findall(html)
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
            if self._looks_like_property(path):
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

    def _looks_like_property(self, path: str) -> bool:
        lower = path.lower()
        return any(re.search(pattern, lower) for pattern in self._PROPERTY_PATTERNS)

    def _is_likely_listing_or_form(self, url: str) -> bool:
        lower = url.lower()
        return any(re.search(pattern, lower) for pattern in self._LISTING_PATTERNS)

    @staticmethod
    def _score_url(url: str) -> int:
        parsed = urlparse(url)
        path = parsed.path or "/"
        score = 0
        # Profundidade do path.
        segments = [s for s in path.split("/") if s]
        score += len(segments) * 10
        # Presença de número no último segmento (provável ID).
        if segments and re.search(r"\d", segments[-1]):
            score += 20
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
