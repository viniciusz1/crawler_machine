from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from crawler_machine.discovery.items_catalog.constants import (
    DEFAULT_PROPERTY_PATTERNS,
    EXCLUDED_NON_PROPERTY_PATTERNS,
    LISTING_ENTRYPOINT_PATH_RE,
    LISTING_ENTRYPOINT_TEXT_RE,
    PAGE_PATH_RE,
    PAGE_QUERY_KEYS,
)
from crawler_machine.discovery.items_catalog.models import PageSnapshot


class URLClassifier:
    """Classifica URLs da página entre imóveis, páginas de entrada de catálogo e rotas ignoradas."""

    def __init__(self, listing_patterns: list[str] | None = None) -> None:
        self._custom_patterns = listing_patterns
        if listing_patterns is None:
            self.property_patterns = list(DEFAULT_PROPERTY_PATTERNS)
        elif len(listing_patterns) == 0:
            self.property_patterns = []
        else:
            merged = list(listing_patterns)
            for pattern in DEFAULT_PROPERTY_PATTERNS:
                if pattern not in merged:
                    merged.append(pattern)
            self.property_patterns = merged

    def should_discover_entrypoints(self, current_url: str, base_url: str) -> bool:
        path = (urlparse(current_url).path or "/").rstrip("/").lower()
        if path in {"", "/inicio", "/home", "/index", "/index.php", "/index.html"}:
            return True
        return self.is_property_url(current_url, base_url, allow_entry=True)

    def collect_property_urls(
        self,
        page_url: str,
        raw_links: list[str],
        *,
        card_links: set[str],
        base_url: str,
        include_subdomains: bool,
        discovered: list[str],
        seen: set[str],
        max_urls: int,
    ) -> int:
        added = 0
        for raw_link in raw_links:
            if not raw_link or raw_link.startswith(("#", "javascript:", "mailto:", "tel:", "whatsapp:")):
                continue
            absolute = normalize_url(urljoin(page_url, raw_link))
            if not same_domain(absolute, base_url, include_subdomains=include_subdomains):
                continue
            is_card = raw_link in card_links
            if not self.is_property_url(absolute, base_url, is_card_link=is_card):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            discovered.append(absolute)
            added += 1
            if len(discovered) >= max_urls:
                break
        return added

    def is_property_url(
        self,
        url: str,
        base_url: str,
        *,
        is_card_link: bool = False,
        allow_entry: bool = False,
    ) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False

        path = parsed.path or "/"
        stripped_path = path.rstrip("/")
        if stripped_path == "":
            return False

        if not allow_entry:
            normalized_base_path = urlparse(base_url).path.rstrip("/")
            if stripped_path == normalized_base_path:
                return False

        target = f"{path}?{parsed.query}" if parsed.query else path

        if any(
            re.search(pattern, target, re.IGNORECASE)
            for pattern in EXCLUDED_NON_PROPERTY_PATTERNS
        ):
            return False

        if LISTING_ENTRYPOINT_PATH_RE.match(path):
            return False

        if self._custom_patterns is not None and len(self._custom_patterns) == 0:
            return True

        if is_card_link:
            return True

        return any(
            re.search(pattern, target, re.IGNORECASE)
            for pattern in self.property_patterns
        )

    def find_listing_entrypoints(
        self,
        snap: PageSnapshot,
        *,
        base_url: str,
        visited_pages: set[str],
        include_subdomains: bool,
    ) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def _add(url_str: str) -> None:
            if url_str not in visited_pages and url_str not in seen:
                seen.add(url_str)
                candidates.append(url_str)

        all_hrefs = [
            *(ctrl.href for ctrl in snap.controls if ctrl.href and not ctrl.disabled),
            *snap.links,
        ]
        for raw_href in all_hrefs:
            if not is_navigating_href(raw_href):
                continue
            candidate_url = normalize_url(urljoin(snap.url, raw_href))
            if not same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            parsed = urlparse(candidate_url)
            if LISTING_ENTRYPOINT_PATH_RE.match(parsed.path or "/"):
                _add(candidate_url)

        for ctrl in snap.controls:
            if ctrl.disabled or not is_navigating_href(ctrl.href):
                continue
            candidate_url = normalize_url(urljoin(snap.url, ctrl.href or ""))
            if not same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self.is_property_url(candidate_url, base_url):
                continue
            parsed = urlparse(candidate_url)
            path = parsed.path or "/"
            label = f"{ctrl.text} {ctrl.aria_label} {ctrl.title}".strip()
            if LISTING_ENTRYPOINT_TEXT_RE.search(label) and not any(
                re.search(p, path, re.IGNORECASE)
                for p in (
                    r"/contato",
                    r"/sobre",
                    r"/empresa",
                    r"/login",
                    r"/admin",
                    r"cadastr",
                    r"anuncie",
                    r"/whatsapp",
                )
            ):
                _add(candidate_url)

        return candidates


def extract_url_page_number(url: str) -> int | None:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    for key in PAGE_QUERY_KEYS:
        values = query.get(key)
        if values and values[0].isdigit():
            return int(values[0])
    path_match = PAGE_PATH_RE.search(parsed.path or "")
    if path_match:
        return int(path_match.group(1))
    return None


def is_navigating_href(href: str | None) -> bool:
    if not href:
        return False
    stripped = href.strip().lower()
    return bool(stripped) and not stripped.startswith(
        ("#", "javascript:", "mailto:", "tel:", "whatsapp:")
    )


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    return parsed._replace(fragment="").geturl()


def same_domain(url: str, base_url: str, *, include_subdomains: bool = False) -> bool:
    host = urlparse(url).netloc.lower().lstrip("www.")
    base_host = urlparse(base_url).netloc.lower().lstrip("www.")
    if not host or not base_host:
        return False
    if host == base_host:
        return True
    if include_subdomains and host.endswith(f".{base_host}"):
        return True
    return False
