from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlparse

from crawler_machine.prospecting.models import Candidate, Place
from crawler_machine.sink.naming import build_source_name


#: Domínios raiz de agregadores, redes sociais e marketplaces que não são
#: alvos de crawling. O operador pode expandir conforme falsos-positivos.
AGGREGATOR_DOMAINS: frozenset[str] = frozenset(
    {
        # portais imobiliários / marketplaces
        "zapimoveis.com.br",
        "vivareal.com.br",
        "imovelweb.com.br",
        "olx.com.br",
        "mercadorural.com.br",
        "netimoveis.com.br",
        "lugarcerto.com.br",
        "trovit.com.br",
        "vivalocal.com.br",
        "chavesnaomao.com.br",
        "mercadoimoveis.com.br",
        "quintoandar.com.br",
        "enjoei.com.br",
        "mercadolivre.com.br",
        "airbnb.com",
        "airbnb.com.br",
        "booking.com",
        # redes sociais e plataformas
        "facebook.com",
        "instagram.com",
        "linkedin.com",
        "twitter.com",
        "x.com",
        "youtube.com",
        "tiktok.com",
        "whatsapp.com",
        "google.com",
        "wikipedia.org",
        "gov.br",
    }
)


#: Sufixos de TLD de dois níveis (usados para extrair o domínio raiz sem
#: depender de bibliotecas externas como ``tldextract``).
_DOUBLE_TLDS: frozenset[str] = frozenset(
    {
        "com.br",
        "net.br",
        "org.br",
        "gov.br",
        "edu.br",
        "mil.br",
        "eco.br",
        "emp.br",
        "ind.br",
        "med.br",
        "nom.br",
        "tv.br",
        "blog.br",
        "wiki.br",
        "com.au",
        "net.au",
        "co.uk",
        "org.uk",
        "co.nz",
    }
)


def root_domain(url: str) -> str:
    """Extrai o domínio raiz de uma URL.

    Exemplos:
        ``https://www.imob.com.br/imovel/1`` -> ``imob.com.br``
        ``https://imob.net`` -> ``imob.net``
        ``https://filial.imob.com.br`` -> ``imob.com.br``
    """
    parsed = urlparse(url if "://" in url else f"http://{url}")
    netloc = (parsed.hostname or "").lower().strip()
    if not netloc:
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    parts = [p for p in netloc.split(".") if p]
    if len(parts) >= 3 and ".".join(parts[-2:]) in _DOUBLE_TLDS:
        return ".".join(parts[-3:])
    if len(parts) >= 2:
        return ".".join(parts[-2:])
    return netloc


def is_aggregator(url: str | None) -> bool:
    """Indica se a URL aponta para um agregador/marketplace/rede social."""
    if not url:
        return False
    return root_domain(url) in AGGREGATOR_DOMAINS


def _candidate(
    place: Place,
    *,
    base_url: str | None,
    status: str,
    reject_reason: str | None,
) -> Candidate:
    source_name = build_source_name(base_url) if base_url else None
    return Candidate(
        city=place.city,
        state=place.state,
        name=place.name,
        base_url=base_url,
        source_name=source_name,
        phone=place.phone,
        address=place.address,
        google_place_id=place.place_id,
        source=place.source,
        status=status,
        reject_reason=reject_reason,
    )


def classify(place: Place) -> Candidate:
    """Transforma um ``Place`` em ``Candidate``, decidindo o status.

    Regras (em ordem):
      1. sem website -> ``rejected`` / ``no_website``
      2. website de agregador -> ``rejected`` / ``aggregator``
      3. caso contrário -> ``candidate``
    """
    website = place.website
    if not website:
        return _candidate(place, base_url=None, status="rejected", reject_reason="no_website")
    if is_aggregator(website):
        return _candidate(place, base_url=website, status="rejected", reject_reason="aggregator")
    return _candidate(place, base_url=website, status="candidate", reject_reason=None)


def dedup_by_domain(candidates: list[Candidate]) -> list[Candidate]:
    """Marca como ``duplicate_domain`` as ocorrências repetidas de um domínio.

    Mantém a primeira ocorrência de cada domínio raiz (com seu status
    original) e rejeita as subsequentes. Candidatos sem ``base_url`` (ex.:
    ``no_website``) não participam da dedup e são preservados como estão.
    """
    seen: set[str] = set()
    result: list[Candidate] = []
    for candidate in candidates:
        domain = root_domain(candidate.base_url) if candidate.base_url else None
        if domain is None or domain == "":
            result.append(candidate)
            continue
        if domain in seen:
            result.append(
                replace(candidate, status="rejected", reject_reason="duplicate_domain")
            )
            continue
        seen.add(domain)
        result.append(candidate)
    return result
