from __future__ import annotations

from urllib.parse import parse_qs, urljoin, urlparse

from crawler_machine.discovery.items_catalog.constants import (
    EXPLICIT_NEXT_WORD_RE,
    LOAD_MORE_CLASS_RE,
    LOAD_MORE_TEXT_PATTERNS,
    NEXT_TEXT_PATTERNS,
    NON_PAGINATION_CONTROL_RE,
    PAGE_PATH_RE,
    PAGE_QUERY_KEYS,
    PAGINATION_NEXT_CLASS_RE,
    VER_MAIS_EXACT_RE,
)
from crawler_machine.discovery.items_catalog.models import (
    PageControl,
    PageSnapshot,
    PaginationAction,
)
from crawler_machine.discovery.items_catalog.url_classifier import (
    URLClassifier,
    extract_url_page_number,
    is_navigating_href,
    normalize_url,
    same_domain,
)


class CatalogPaginator:
    """Identifica o mecanismo de paginação da listagem (load more, próxima URL ou botão JS)."""

    def __init__(self, classifier: URLClassifier) -> None:
        self._classifier = classifier

    @staticmethod
    def detect_active_page_number(snap: PageSnapshot, fallback: int) -> int:
        for ctrl in snap.controls:
            if ctrl.is_active and ctrl.in_pagination and ctrl.text.isdigit():
                return int(ctrl.text)
        for ctrl in snap.controls:
            if ctrl.is_active and ctrl.text.isdigit() and not NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                return int(ctrl.text)
        parsed = urlparse(snap.url)
        query = parse_qs(parsed.query)
        for key in PAGE_QUERY_KEYS:
            values = query.get(key)
            if values and values[0].isdigit():
                return int(values[0])
        path_match = PAGE_PATH_RE.search(parsed.path or "")
        if path_match:
            return int(path_match.group(1))
        return fallback

    def detect_pagination_action(
        self,
        snap: PageSnapshot,
        *,
        base_url: str,
        current_page: int,
        visited_pages: set[str],
        include_subdomains: bool,
    ) -> PaginationAction | None:
        # 1. Verifica botão "Carregar mais" / "Mostrar mais Imóveis"
        for ctrl in snap.controls:
            if ctrl.disabled:
                continue
            if self.is_load_more_control(ctrl, snap.url, base_url):
                return PaginationAction(kind="load_more", control_id=ctrl.control_id)

        # 2. Verifica próxima página via URL (rel="next", texto "Próxima"/">" ou página N+1)
        next_url = self.find_next_page_url(
            snap,
            base_url=base_url,
            current_page=current_page,
            visited_pages=visited_pages,
            include_subdomains=include_subdomains,
        )
        if next_url is not None:
            return PaginationAction(kind="next_url", url=next_url)

        # 3. Verifica botão JS de próxima página (sem href navegável)
        next_button_id = self.find_next_page_button(snap, current_page=current_page)
        if next_button_id is not None:
            return PaginationAction(kind="next_button", control_id=next_button_id)

        return None

    def is_load_more_control(
        self,
        ctrl: PageControl,
        page_url: str,
        base_url: str,
    ) -> bool:
        if ctrl.tag == "link":
            return False
        if NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
            return False
        if ctrl.href and is_navigating_href(ctrl.href):
            resolved = normalize_url(urljoin(page_url, ctrl.href))
            if self._classifier.is_property_url(resolved, base_url):
                return False

        label = f"{ctrl.text} {ctrl.aria_label} {ctrl.title}".strip()
        if LOAD_MORE_TEXT_PATTERNS.search(label):
            return True

        if LOAD_MORE_CLASS_RE.search(ctrl.classes):
            return True

        if VER_MAIS_EXACT_RE.match(ctrl.text.strip()):
            if ctrl.tag == "button" or not is_navigating_href(ctrl.href):
                return True

        return False

    def find_next_page_url(
        self,
        snap: PageSnapshot,
        *,
        base_url: str,
        current_page: int,
        visited_pages: set[str],
        include_subdomains: bool,
    ) -> str | None:
        target_next_page = current_page + 1

        # Prioridade 2a: rel="next", classe explícita de next pagination ou texto "Próxima"
        for ctrl in snap.controls:
            if ctrl.disabled or not is_navigating_href(ctrl.href):
                continue
            if NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            candidate_url = normalize_url(urljoin(snap.url, ctrl.href or ""))
            if candidate_url in visited_pages:
                continue
            if not same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self._classifier.is_property_url(candidate_url, base_url):
                continue

            if "next" in ctrl.rel.lower():
                return candidate_url

            if PAGINATION_NEXT_CLASS_RE.search(ctrl.classes):
                return candidate_url

            for candidate_label in (ctrl.text, ctrl.aria_label, ctrl.title):
                cleaned = candidate_label.strip()
                if cleaned and NEXT_TEXT_PATTERNS.match(cleaned):
                    return candidate_url

        # Prioridade 2b: Link numérico para (current_page + 1) ou query/path de próxima página
        for ctrl in snap.controls:
            if ctrl.disabled or not is_navigating_href(ctrl.href):
                continue
            if NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            candidate_url = normalize_url(urljoin(snap.url, ctrl.href or ""))
            if candidate_url in visited_pages:
                continue
            if not same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self._classifier.is_property_url(candidate_url, base_url):
                continue

            if ctrl.text.strip() == str(target_next_page) and (
                ctrl.in_pagination or extract_url_page_number(candidate_url) == target_next_page
            ):
                return candidate_url

            if extract_url_page_number(candidate_url) == target_next_page:
                return candidate_url

        return None

    @staticmethod
    def find_next_page_button(
        snap: PageSnapshot,
        *,
        current_page: int,
    ) -> str | None:
        target_next_page = current_page + 1

        # Prioridade 3a: Botão numérico para (current_page + 1) dentro de container de paginação
        for ctrl in snap.controls:
            if ctrl.disabled or ctrl.tag == "link":
                continue
            if is_navigating_href(ctrl.href):
                continue
            if NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            if ctrl.in_pagination and ctrl.text.strip() == str(target_next_page):
                return ctrl.control_id

        # Prioridade 3b: Botão de próxima página por texto/aria-label
        for ctrl in snap.controls:
            if ctrl.disabled or ctrl.tag == "link":
                continue
            if is_navigating_href(ctrl.href):
                continue
            if NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            for candidate_label in (ctrl.text, ctrl.aria_label, ctrl.title):
                cleaned = candidate_label.strip()
                if not cleaned:
                    continue
                if EXPLICIT_NEXT_WORD_RE.match(cleaned):
                    return ctrl.control_id
                if ctrl.in_pagination and NEXT_TEXT_PATTERNS.match(cleaned):
                    return ctrl.control_id
        return None
