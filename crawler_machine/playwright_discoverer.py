from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, AsyncIterator, Callable, Protocol
from urllib.parse import parse_qs, urljoin, urlparse

logger = logging.getLogger(__name__)

_DEFAULT_PROPERTY_PATTERNS = [
    r"/imovel/",
    r"/imovel-",
    r"/imoveis/detalhes",
    r"/\d{3,}/?(?:\?.*)?$",
    r"/detalhes_(?:loc|vd)\.php\?imovel=\d+",
    r"/(?:comprar|alugar|vender)/[^/]+/\d+",
    r"/(?:comprar|alugar|vender)/.+",
]

_EXCLUDED_NON_PROPERTY_PATTERNS = [
    r"^/imoveis/?$",
    r"^/imoveis/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/imovel/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/(?:comprar|alugar|aluguel|vender|locacao|venda)/?$",
    r"^/(?:venda|aluguel|locacao)/(?:imovel|apartamento|casa|terreno|cobertura|comercial|galpao)",
    r"/filtro/",
    r"cadastr",
    r"encomend",
    r"solicite",
    r"anuncie",
    r"financi",
    r"trabalhe-conosco",
    r"ouvidoria",
    r"nossa-equipe",
    r"quem-somos",
    r"conheca-a-cidade",
    r"nossos-diferenciais",
    r"nossos-profissionais",
    r"como-alugar",
    r"indice-de-reajuste",
    r"assessoria-juridica",
    r"quero-alugar-ou-vender",
    r"area-do-cliente",
    r"/whatsapp",
    r"/blog(?:/|$)",
    r"/corretores",
    r"/institucional",
    r"/documentos",
    r"/condominios/?$",
    r"/busca/?$",
    r"/contato",
    r"/sobre",
    r"/empresa",
    r"/favorito",
    r"/login",
    r"/admin",
    r"/politica",
    r"/privacidade",
    r"/termos",
    r"todos-os-bairros",
    r"todas-as-opcoes",
    r"ordenacao=",
    r"(?:^|[?&])(pagina|page|pg|p)=\d+",
    r"(?:/|-|_)(?:page|pagina)(?:/|-|_)\d+/?$",
]

_NEXT_TEXT_PATTERNS = re.compile(
    r"^(?:pr[oó]xim[ao](?:\s+p[aá]gina)?|seguinte|avan[cç]ar|next(?:\s+page)?|"
    r">|>>|»|›|→|pr[oó]xim[ao]\s*(?:>|>>|»|›|→))$",
    re.IGNORECASE,
)

_EXPLICIT_NEXT_WORD_RE = re.compile(
    r"^(?:pr[oó]xim[ao](?:\s+p[aá]gina)?|seguinte|next(?:\s+page)?|"
    r"pr[oó]xim[ao]\s*(?:>|>>|»|›|→))$",
    re.IGNORECASE,
)

_LOAD_MORE_TEXT_PATTERNS = re.compile(
    r"(?:carregar\s+mais|ver\s+mais\s+im[oó]veis|mostrar\s+mais|"
    r"mais\s+im[oó]veis|exibir\s+mais|load\s+more|carregar\s*\+)",
    re.IGNORECASE,
)

_VER_MAIS_EXACT_RE = re.compile(r"^(?:ver\s+mais|veja\s+mais)$", re.IGNORECASE)

_PAGINATION_CONTAINER_RE = re.compile(
    r"(?:paginat|paginacao|pagina[cç][aã]o|page-numbers|wp-pagenavi|nav-links|pager|"
    r"jetpagination|PageNumber|BtnShowMoreImovel|BoxBtnShowMoreImovel)",
    re.IGNORECASE,
)

_PAGINATION_NEXT_CLASS_RE = re.compile(
    r"(?:jetpagination__next|list__next-btn|page-next|next-page|pagination-next)",
    re.IGNORECASE,
)

_NON_PAGINATION_CONTROL_RE = re.compile(
    r"(?:owl-|slick-|swiper-|carousel|slider|banner|card-img|card-btn|modal|"
    r"agendar|ag-data|cookie|whatsapp|wpp|primeiraPagina|ultimaPagina|"
    r"first-page|last-page|previous|prev-btn|botao_tipo_busca)",
    re.IGNORECASE,
)

_LOAD_MORE_CLASS_RE = re.compile(
    r"(?:load-more|loadmore|carregar-mais|btn-more|show-more|BtnShowMoreImovel|infinite-scroll)",
    re.IGNORECASE,
)

_PROPERTY_CARD_LINK_CLASS_RE = re.compile(
    r"(?:ImovelLinkClick|VejaMais|ui__card-link|meuLink|card-imovel|imovel-card|property-card)",
    re.IGNORECASE,
)

_PAGE_QUERY_KEYS = ("pagina", "page", "pg", "p")
_PAGE_PATH_RE = re.compile(
    r"(?:/|-|_)(?:page|pagina)(?:/|-|_)(\d+)(?:/|$)",
    re.IGNORECASE,
)

_LISTING_ENTRYPOINT_PATH_RE = re.compile(
    r"^/(?:imoveis|imovel/(?:comprar|alugar|aluguel|vender|locacao|venda)|"
    r"imoveis/(?:comprar|alugar|aluguel|vender|locacao|venda|a-venda|para-alugar)|"
    r"comprar|alugar|aluguel|vender|locacao|venda|busca|buscar-imoveis)/?$",
    re.IGNORECASE,
)

_LISTING_ENTRYPOINT_TEXT_RE = re.compile(
    r"(?:ver\s+todos(?:\s+os)?\s+im[oó]veis|todos\s+os\s+im[oó]veis|"
    r"ver\s+mais\s+im[oó]veis|buscar\s+im[oó]veis|nossos\s+im[oó]veis|"
    r"im[oó]veis\s+[aà]\s+venda|im[oó]veis\s+para\s+alugar|"
    r"^im[oó]veis$|^comprar$|^alugar$|^venda$|^loca[cç][aã]o$)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class PageControl:
    """Elemento interativo (link ou botão) presente no DOM da página."""

    control_id: str
    tag: str
    text: str
    href: str | None = None
    rel: str = ""
    aria_label: str = ""
    title: str = ""
    classes: str = ""
    in_pagination: bool = False
    is_active: bool = False
    disabled: bool = False
    in_chrome: bool = False


@dataclass(frozen=True)
class PageSnapshot:
    """Estado inspecionado de uma página após renderização e scroll."""

    url: str
    html: str
    links: list[str] = field(default_factory=list)
    controls: list[PageControl] = field(default_factory=list)
    card_links: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PaginationAction:
    """Ação identificada para avançar na listagem de imóveis."""

    kind: str  # "load_more" | "next_url" | "next_button"
    url: str | None = None
    control_id: str | None = None


class ListingBrowserSession(Protocol):
    """Sessão de navegador capaz de navegar, rolar até o fim e interagir com o paginador."""

    async def goto(self, url: str) -> None: ...
    async def scroll_to_bottom(self) -> list[str]: ...
    async def snapshot(self) -> PageSnapshot: ...
    async def click(self, control_id: str) -> bool: ...


class ListingBrowser(Protocol):
    """Fábrica de sessão de navegador para discovery de listagem."""

    def session(self) -> AsyncIterator[ListingBrowserSession]: ...


class _DOMInspectorParser(HTMLParser):
    """Extrai links e controles interativos de um documento HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.card_links: list[str] = []
        self.controls: list[PageControl] = []
        self._stack: list[tuple[str, dict[str, str]]] = []
        self._current_control: dict[str, Any] | None = None
        self._control_counter = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        self._stack.append((tag_lower, attr_map))

        if tag_lower in {"a", "link"} and attr_map.get("href"):
            href = attr_map["href"].strip()
            if tag_lower == "a":
                in_chrome = self._in_chrome_context()
                cls_str = attr_map.get("class", "")
                if _PROPERTY_CARD_LINK_CLASS_RE.search(cls_str):
                    self.card_links.append(href)
                    self.links.append(href)
                elif not in_chrome:
                    self.links.append(href)
                elif _LISTING_ENTRYPOINT_PATH_RE.match(urlparse(href).path or ""):
                    self.links.append(href)
            elif "next" in attr_map.get("rel", "").lower():
                self.controls.append(
                    PageControl(
                        control_id=f"link-{self._control_counter}",
                        tag="link",
                        text="",
                        href=href,
                        rel=attr_map.get("rel", ""),
                        in_pagination=True,
                    )
                )
                self._control_counter += 1

        has_pw_id = bool(attr_map.get("data-cm-control-id"))
        cls_and_id = f"{attr_map.get('class', '')} {attr_map.get('id', '')}"
        is_pagination_div = (
            tag_lower in {"div", "span", "li"}
            and bool(re.search(r"(?:btn-paginacao|PageNumber|page-numbers)", cls_and_id, re.IGNORECASE))
        )
        is_interactive = (
            has_pw_id
            or tag_lower in {"a", "button"}
            or attr_map.get("role", "").lower() == "button"
            or (
                tag_lower == "input"
                and attr_map.get("type", "").lower() in {"button", "submit"}
            )
            or is_pagination_div
            or (
                tag_lower == "span"
                and self._is_active_attrs(attr_map)
                and self._in_pagination_context()
            )
        )
        if is_interactive and self._current_control is None:
            control_id = attr_map.get("data-cm-control-id") or f"ctrl-{self._control_counter}"
            self._control_counter += 1
            self._current_control = {
                "control_id": control_id,
                "tag": tag_lower,
                "text_parts": [attr_map.get("value", "")] if tag_lower == "input" else [],
                "href": attr_map.get("href") or None,
                "rel": attr_map.get("rel", ""),
                "aria_label": attr_map.get("aria-label", ""),
                "title": attr_map.get("title", ""),
                "classes": self._combined_classes(attr_map),
                "in_pagination": self._in_pagination_context(),
                "is_active": self._is_active_in_stack(),
                "disabled": self._is_disabled_in_stack(),
                "in_chrome": self._in_chrome_context(),
            }

    def handle_data(self, data: str) -> None:
        if self._current_control is not None:
            self._current_control["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        if self._current_control is not None and self._current_control["tag"] == tag_lower:
            raw_text = " ".join(self._current_control["text_parts"])
            clean_text = re.sub(r"\s+", " ", html_lib.unescape(raw_text)).strip()
            self.controls.append(
                PageControl(
                    control_id=self._current_control["control_id"],
                    tag=self._current_control["tag"],
                    text=clean_text,
                    href=self._current_control["href"],
                    rel=self._current_control["rel"],
                    aria_label=self._current_control["aria_label"],
                    title=self._current_control["title"],
                    classes=self._current_control["classes"],
                    in_pagination=self._current_control["in_pagination"],
                    is_active=self._current_control["is_active"],
                    disabled=self._current_control["disabled"],
                    in_chrome=self._current_control["in_chrome"],
                )
            )
            self._current_control = None

        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx][0] == tag_lower:
                self._stack.pop(idx)
                break

    def _in_pagination_context(self) -> bool:
        for tag, attrs in self._stack:
            combined = f"{attrs.get('class', '')} {attrs.get('id', '')} {attrs.get('aria-label', '')} {attrs.get('role', '')}"
            if _PAGINATION_CONTAINER_RE.search(combined):
                return True
            if tag == "nav" and not re.search(r"(?:menu|header|top|navbar)", combined, re.IGNORECASE):
                return True
        return False

    def _in_chrome_context(self) -> bool:
        for tag, attrs in self._stack:
            if tag in {"header", "footer", "nav"}:
                return True
            combined = f"{attrs.get('class', '')} {attrs.get('id', '')}"
            if re.search(r"(?:^|\s|_|-)footer(?:\s|_|-|$)|box_link_mais_filtros", combined, re.IGNORECASE):
                return True
        return False

    def _combined_classes(self, current_attrs: dict[str, str]) -> str:
        classes = [current_attrs.get("class", ""), current_attrs.get("id", "")]
        if len(self._stack) >= 2:
            parent_tag, parent_attrs = self._stack[-2]
            if parent_tag in {"li", "span", "div"}:
                classes.append(parent_attrs.get("class", ""))
                classes.append(parent_attrs.get("id", ""))
        return " ".join(c for c in classes if c).strip()

    def _is_active_in_stack(self) -> bool:
        for tag, attrs in self._stack[-2:]:
            if tag in {"a", "button", "li", "span", "div"} and self._is_active_attrs(attrs):
                return True
        return False

    @staticmethod
    def _is_active_attrs(attrs: dict[str, str]) -> bool:
        if attrs.get("aria-current", "").lower() in {"page", "true"}:
            return True
        classes = f" {attrs.get('class', '').lower()} "
        return any(token in classes for token in (" active ", " current ", " selected ", " is-active "))

    def _is_disabled_in_stack(self) -> bool:
        for tag, attrs in self._stack[-2:]:
            if tag in {"a", "button", "li", "span", "input", "div"}:
                if "disabled" in attrs or attrs.get("aria-disabled", "").lower() == "true":
                    return True
                classes = f" {attrs.get('class', '').lower()} "
                if (
                    " disabled " in classes
                    or " is-disabled " in classes
                    or "--disabled" in classes
                ):
                    return True
        return False


def parse_page_snapshot(url: str, html: str) -> PageSnapshot:
    """Constrói um ``PageSnapshot`` a partir de URL e HTML renderizado."""
    parser = _DOMInspectorParser()
    parser.feed(html)
    json_links = re.findall(r'["\']link["\']\s*:\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    all_links = [*parser.links, *json_links]
    return PageSnapshot(
        url=url,
        html=html,
        links=all_links,
        controls=parser.controls,
        card_links=parser.card_links,
    )


class FakeListingBrowser:
    """Implementação em memória de ``ListingBrowser`` para testes determinísticos."""

    def __init__(
        self,
        pages: dict[str, str],
        on_click: Callable[[str, PageControl], str | None] | None = None,
        scroll_links: dict[str, list[str]] | None = None,
    ) -> None:
        self._pages = dict(pages)
        self._on_click = on_click
        self._scroll_links = dict(scroll_links or {})
        self.visited_urls: list[str] = []
        self.clicked_controls: list[str] = []
        self.scroll_count = 0

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ListingBrowserSession]:
        yield _FakeListingBrowserSession(self)


class _FakeListingBrowserSession:
    def __init__(self, browser: FakeListingBrowser) -> None:
        self._browser = browser
        self._current_url = ""
        self._current_html = ""

    async def goto(self, url: str) -> None:
        self._current_url = url
        self._browser.visited_urls.append(url)
        self._current_html = self._browser._pages.get(url, "")

    async def scroll_to_bottom(self) -> list[str]:
        self._browser.scroll_count += 1
        return list(self._browser._scroll_links.get(self._current_url, []))

    async def snapshot(self) -> PageSnapshot:
        return parse_page_snapshot(self._current_url, self._current_html)

    async def click(self, control_id: str) -> bool:
        snap = parse_page_snapshot(self._current_url, self._current_html)
        control = next((c for c in snap.controls if c.control_id == control_id), None)
        if control is None or control.disabled:
            return False
        self._browser.clicked_controls.append(control_id)
        if self._browser._on_click is not None:
            updated_html = self._browser._on_click(self._current_url, control)
            if updated_html is not None:
                self._current_html = updated_html
                return True
        return False


class PlaywrightListingDiscoverer:
    """Descobre URLs de imóveis navegando na listagem e paginando via Playwright."""

    def __init__(
        self,
        browser: ListingBrowser | None = None,
        max_urls: int = 5000,
        max_pages: int = 100,
        listing_patterns: list[str] | None = None,
    ) -> None:
        self._browser = browser
        self.max_urls = max_urls
        self.max_pages = max_pages
        self._custom_patterns = listing_patterns
        if listing_patterns is None:
            self._property_patterns = list(_DEFAULT_PROPERTY_PATTERNS)
        elif len(listing_patterns) == 0:
            self._property_patterns = []
        else:
            merged = list(listing_patterns)
            for pattern in _DEFAULT_PROPERTY_PATTERNS:
                if pattern not in merged:
                    merged.append(pattern)
            self._property_patterns = merged

    async def discover(
        self,
        base_url: str,
        policy: dict[str, Any] | None = None,
    ) -> list[str]:
        """Percorre a listagem de imóveis e páginas seguintes até acabar os imóveis."""
        policy = policy or {}
        config = policy.get("configuration")
        options = dict(config) if isinstance(config, dict) else {}
        max_urls = int(policy.get("max_urls", options.get("max_urls", self.max_urls)))
        max_pages = int(policy.get("max_pages", options.get("max_pages", self.max_pages)))
        include_subdomains = bool(
            policy.get("include_subdomains", options.get("include_subdomains", False))
        )

        browser = self._browser or PlaywrightListingBrowser()
        discovered: list[str] = []
        seen_properties: set[str] = set()
        visited_pages: set[str] = set()

        async with browser.session() as session:
            queue = [base_url]
            pages_visited = 0

            while queue and len(discovered) < max_urls and pages_visited < max_pages:
                entry_url = queue.pop(0)
                normalized_entry = self._normalize_url(entry_url)
                if normalized_entry in visited_pages:
                    continue

                await session.goto(entry_url)
                current_page_num = 1
                is_initial_entry = normalized_entry == self._normalize_url(base_url)

                while len(discovered) < max_urls and pages_visited < max_pages:
                    pages_visited += 1
                    scroll_links = await session.scroll_to_bottom()
                    snap = await session.snapshot()
                    visited_pages.add(self._normalize_url(snap.url))

                    if is_initial_entry and current_page_num == 1:
                        if self._is_property_url(snap.url, base_url, allow_entry=True):
                            normalized_self = self._normalize_url(snap.url)
                            if normalized_self not in seen_properties:
                                seen_properties.add(normalized_self)
                                discovered.append(normalized_self)

                    new_count = self._collect_property_urls(
                        snap.url,
                        [*snap.card_links, *snap.links, *scroll_links],
                        card_links=set(snap.card_links),
                        base_url=base_url,
                        include_subdomains=include_subdomains,
                        discovered=discovered,
                        seen=seen_properties,
                        max_urls=max_urls,
                    )

                    if is_initial_entry and current_page_num == 1 and self._should_discover_entrypoints(snap.url, base_url):
                        entrypoints = self._find_listing_entrypoints(
                            snap,
                            base_url=base_url,
                            visited_pages=visited_pages,
                            include_subdomains=include_subdomains,
                        )
                        for listing_url in entrypoints:
                            if listing_url not in queue:
                                queue.append(listing_url)

                        if entrypoints or self._is_property_url(snap.url, base_url, allow_entry=True):
                            break

                    active_page = self._detect_active_page_number(snap, current_page_num)
                    action = self._detect_pagination_action(
                        snap,
                        base_url=base_url,
                        current_page=active_page,
                        visited_pages=visited_pages,
                        include_subdomains=include_subdomains,
                    )

                    if action is None:
                        break

                    if new_count == 0 and current_page_num > 1:
                        break

                    if action.kind == "next_url" and action.url:
                        await session.goto(action.url)
                        current_page_num = active_page + 1
                        continue

                    if action.kind in {"load_more", "next_button"} and action.control_id:
                        clicked = await session.click(action.control_id)
                        if not clicked:
                            break
                        current_page_num = active_page + 1
                        continue

                    break

        return discovered[:max_urls]

    def discover_sync(
        self,
        base_url: str,
        policy: dict[str, Any] | None = None,
    ) -> list[str]:
        """Versão síncrona de ``discover``."""
        return asyncio.run(self.discover(base_url, policy))

    def _should_discover_entrypoints(self, current_url: str, base_url: str) -> bool:
        path = (urlparse(current_url).path or "/").rstrip("/")
        if path == "":
            return True
        return self._is_property_url(current_url, base_url, allow_entry=True)

    def _collect_property_urls(
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
            absolute = self._normalize_url(urljoin(page_url, raw_link))
            if not self._same_domain(absolute, base_url, include_subdomains=include_subdomains):
                continue
            is_card = raw_link in card_links
            if not self._is_property_url(absolute, base_url, is_card_link=is_card):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            discovered.append(absolute)
            added += 1
            if len(discovered) >= max_urls:
                break
        return added

    def _is_property_url(
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
            for pattern in _EXCLUDED_NON_PROPERTY_PATTERNS
        ):
            return False

        if _LISTING_ENTRYPOINT_PATH_RE.match(path):
            return False

        if self._custom_patterns is not None and len(self._custom_patterns) == 0:
            return True

        if is_card_link:
            return True

        return any(
            re.search(pattern, target, re.IGNORECASE)
            for pattern in self._property_patterns
        )

    @staticmethod
    def _detect_active_page_number(snap: PageSnapshot, fallback: int) -> int:
        for ctrl in snap.controls:
            if ctrl.is_active and ctrl.in_pagination and ctrl.text.isdigit():
                return int(ctrl.text)
        for ctrl in snap.controls:
            if ctrl.is_active and ctrl.text.isdigit() and not _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                return int(ctrl.text)
        parsed = urlparse(snap.url)
        query = parse_qs(parsed.query)
        for key in _PAGE_QUERY_KEYS:
            values = query.get(key)
            if values and values[0].isdigit():
                return int(values[0])
        path_match = _PAGE_PATH_RE.search(parsed.path or "")
        if path_match:
            return int(path_match.group(1))
        return fallback

    def _detect_pagination_action(
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
            if self._is_load_more_control(ctrl, snap.url, base_url):
                return PaginationAction(kind="load_more", control_id=ctrl.control_id)

        # 2. Verifica próxima página via URL (rel="next", texto "Próxima"/">" ou página N+1)
        next_url = self._find_next_page_url(
            snap,
            base_url=base_url,
            current_page=current_page,
            visited_pages=visited_pages,
            include_subdomains=include_subdomains,
        )
        if next_url is not None:
            return PaginationAction(kind="next_url", url=next_url)

        # 3. Verifica botão JS de próxima página (sem href navegável)
        next_button_id = self._find_next_page_button(snap, current_page=current_page)
        if next_button_id is not None:
            return PaginationAction(kind="next_button", control_id=next_button_id)

        return None

    def _is_load_more_control(
        self,
        ctrl: PageControl,
        page_url: str,
        base_url: str,
    ) -> bool:
        if ctrl.tag == "link":
            return False
        if _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
            return False
        if ctrl.href and self._is_navigating_href(ctrl.href):
            resolved = self._normalize_url(urljoin(page_url, ctrl.href))
            if self._is_property_url(resolved, base_url):
                return False

        label = f"{ctrl.text} {ctrl.aria_label} {ctrl.title}".strip()
        if _LOAD_MORE_TEXT_PATTERNS.search(label):
            return True

        if _LOAD_MORE_CLASS_RE.search(ctrl.classes):
            return True

        if _VER_MAIS_EXACT_RE.match(ctrl.text.strip()):
            if ctrl.tag == "button" or not self._is_navigating_href(ctrl.href):
                return True

        return False

    def _find_next_page_url(
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
            if ctrl.disabled or not self._is_navigating_href(ctrl.href):
                continue
            if _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            candidate_url = self._normalize_url(urljoin(snap.url, ctrl.href or ""))
            if candidate_url in visited_pages:
                continue
            if not self._same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self._is_property_url(candidate_url, base_url):
                continue

            if "next" in ctrl.rel.lower():
                return candidate_url

            if _PAGINATION_NEXT_CLASS_RE.search(ctrl.classes):
                return candidate_url

            for candidate_label in (ctrl.text, ctrl.aria_label, ctrl.title):
                cleaned = candidate_label.strip()
                if cleaned and _NEXT_TEXT_PATTERNS.match(cleaned):
                    return candidate_url

        # Prioridade 2b: Link numérico para (current_page + 1) ou query/path de próxima página
        for ctrl in snap.controls:
            if ctrl.disabled or not self._is_navigating_href(ctrl.href):
                continue
            if _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            candidate_url = self._normalize_url(urljoin(snap.url, ctrl.href or ""))
            if candidate_url in visited_pages:
                continue
            if not self._same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self._is_property_url(candidate_url, base_url):
                continue

            if ctrl.text.strip() == str(target_next_page) and (
                ctrl.in_pagination or self._extract_url_page_number(candidate_url) == target_next_page
            ):
                return candidate_url

            if self._extract_url_page_number(candidate_url) == target_next_page:
                return candidate_url

        return None

    def _find_next_page_button(
        self,
        snap: PageSnapshot,
        *,
        current_page: int,
    ) -> str | None:
        target_next_page = current_page + 1

        # Prioridade 3a: Botão numérico para (current_page + 1) dentro de container de paginação
        for ctrl in snap.controls:
            if ctrl.disabled or ctrl.tag == "link":
                continue
            if self._is_navigating_href(ctrl.href):
                continue
            if _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            if ctrl.in_pagination and ctrl.text.strip() == str(target_next_page):
                return ctrl.control_id

        # Prioridade 3b: Botão de próxima página por texto/aria-label
        for ctrl in snap.controls:
            if ctrl.disabled or ctrl.tag == "link":
                continue
            if self._is_navigating_href(ctrl.href):
                continue
            if _NON_PAGINATION_CONTROL_RE.search(ctrl.classes):
                continue
            for candidate_label in (ctrl.text, ctrl.aria_label, ctrl.title):
                cleaned = candidate_label.strip()
                if not cleaned:
                    continue
                if _EXPLICIT_NEXT_WORD_RE.match(cleaned):
                    return ctrl.control_id
                if ctrl.in_pagination and _NEXT_TEXT_PATTERNS.match(cleaned):
                    return ctrl.control_id
        return None

    def _find_listing_entrypoints(
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

        # 1. Links e controles com path canônico de listagem (/imoveis, /imoveis/venda, /venda, /aluguel, etc.)
        all_hrefs = [
            *(ctrl.href for ctrl in snap.controls if ctrl.href and not ctrl.disabled),
            *snap.links,
        ]
        for raw_href in all_hrefs:
            if not self._is_navigating_href(raw_href):
                continue
            candidate_url = self._normalize_url(urljoin(snap.url, raw_href))
            if not self._same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            parsed = urlparse(candidate_url)
            if _LISTING_ENTRYPOINT_PATH_RE.match(parsed.path or "/"):
                _add(candidate_url)

        # 2. Controles cujo texto indica entrada de catálogo ("Ver todos os imóveis", "Buscar imóveis", etc.)
        for ctrl in snap.controls:
            if ctrl.disabled or not self._is_navigating_href(ctrl.href):
                continue
            candidate_url = self._normalize_url(urljoin(snap.url, ctrl.href or ""))
            if not self._same_domain(candidate_url, base_url, include_subdomains=include_subdomains):
                continue
            if self._is_property_url(candidate_url, base_url):
                continue
            parsed = urlparse(candidate_url)
            path = parsed.path or "/"
            label = f"{ctrl.text} {ctrl.aria_label} {ctrl.title}".strip()
            if _LISTING_ENTRYPOINT_TEXT_RE.search(label) and not any(
                re.search(p, path, re.IGNORECASE)
                for p in (r"/contato", r"/sobre", r"/empresa", r"/login", r"/admin", r"cadastr", r"anuncie", r"/whatsapp")
            ):
                _add(candidate_url)

        return candidates

    @staticmethod
    def _extract_url_page_number(url: str) -> int | None:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        for key in _PAGE_QUERY_KEYS:
            values = query.get(key)
            if values and values[0].isdigit():
                return int(values[0])
        path_match = _PAGE_PATH_RE.search(parsed.path or "")
        if path_match:
            return int(path_match.group(1))
        return None

    @staticmethod
    def _is_navigating_href(href: str | None) -> bool:
        if not href:
            return False
        stripped = href.strip().lower()
        return bool(stripped) and not stripped.startswith(
            ("#", "javascript:", "mailto:", "tel:", "whatsapp:")
        )

    @staticmethod
    def _normalize_url(url: str) -> str:
        parsed = urlparse(url)
        return parsed._replace(fragment="").geturl()

    @staticmethod
    def _same_domain(url: str, base_url: str, *, include_subdomains: bool = False) -> bool:
        host = urlparse(url).netloc.lower().lstrip("www.")
        base_host = urlparse(base_url).netloc.lower().lstrip("www.")
        if not host or not base_host:
            return False
        if host == base_host:
            return True
        if include_subdomains and host.endswith(f".{base_host}"):
            return True
        return False


class PlaywrightListingBrowser:
    """Implementação real de ``ListingBrowser`` usando ``playwright.async_api``."""

    def __init__(
        self,
        headless: bool = True,
        page_timeout_ms: int = 45000,
        scroll_pause_ms: int = 350,
        max_scroll_steps: int = 12,
    ) -> None:
        self._headless = headless
        self._page_timeout_ms = page_timeout_ms
        self._scroll_pause_ms = scroll_pause_ms
        self._max_scroll_steps = max_scroll_steps

    @asynccontextmanager
    async def session(self) -> AsyncIterator[ListingBrowserSession]:
        from playwright.async_api import async_playwright

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=self._headless)
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
            )
            page = await context.new_page()
            page.set_default_timeout(self._page_timeout_ms)
            try:
                yield _PlaywrightListingBrowserSession(
                    page=page,
                    scroll_pause_ms=self._scroll_pause_ms,
                    max_scroll_steps=self._max_scroll_steps,
                )
            finally:
                await context.close()
                await browser.close()


class _PlaywrightListingBrowserSession:
    def __init__(
        self,
        page: Any,
        scroll_pause_ms: int = 350,
        max_scroll_steps: int = 12,
    ) -> None:
        self._page = page
        self._scroll_pause_ms = scroll_pause_ms
        self._max_scroll_steps = max_scroll_steps

    async def goto(self, url: str) -> None:
        await self._page.goto(url, wait_until="domcontentloaded")
        try:
            await self._page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:
            pass

    async def scroll_to_bottom(self) -> list[str]:
        collected_hrefs: list[str] = []
        previous_height = 0
        for _ in range(self._max_scroll_steps):
            hrefs, height = await self._page.evaluate(
                """() => {
                    const links = Array.from(document.querySelectorAll('a[href]'))
                        .filter(a => !a.closest('header, footer, nav'))
                        .map(a => a.getAttribute('href'))
                        .filter(Boolean);
                    window.scrollTo(0, document.body.scrollHeight);
                    return [links, document.body.scrollHeight || 0];
                }"""
            )
            collected_hrefs.extend(hrefs)
            await self._page.wait_for_timeout(self._scroll_pause_ms)
            new_height = await self._page.evaluate("() => document.body.scrollHeight || 0")
            if new_height == height and height == previous_height:
                break
            previous_height = new_height
        return collected_hrefs

    async def snapshot(self) -> PageSnapshot:
        await self._page.evaluate(
            """() => {
                let counter = 0;
                const selector = [
                    'a',
                    'button',
                    '[role="button"]',
                    'input[type="button"]',
                    'input[type="submit"]',
                    '.btn-paginacao',
                    '.PageNumber',
                    '.BtnShowMoreImovel',
                    '[class*="load-more"]',
                    '[class*="carregar-mais"]'
                ].join(', ');
                const candidates = document.querySelectorAll(selector);
                for (const el of candidates) {
                    const tag = el.tagName.toLowerCase();
                    if (
                        (tag === 'div' || tag === 'span' || tag === 'li') &&
                        el.querySelector('a, button, .btn-paginacao')
                    ) {
                        el.removeAttribute('data-cm-control-id');
                        continue;
                    }
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const visible = (
                        rect.width > 0 &&
                        rect.height > 0 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none'
                    );
                    if (visible) {
                        el.setAttribute('data-cm-control-id', `pw-${counter++}`);
                    } else {
                        el.removeAttribute('data-cm-control-id');
                    }
                }
            }"""
        )
        html = await self._page.content()
        snap = parse_page_snapshot(self._page.url, html)
        visible_controls = [
            ctrl
            for ctrl in snap.controls
            if ctrl.tag == "link"
            or ctrl.control_id.startswith("pw-")
            or (ctrl.is_active and ctrl.in_pagination)
        ]
        return PageSnapshot(
            url=snap.url,
            html=snap.html,
            links=snap.links,
            controls=visible_controls,
            card_links=snap.card_links,
        )

    async def click(self, control_id: str) -> bool:
        locator = self._page.locator(f'[data-cm-control-id="{control_id}"]').first
        if await locator.count() == 0:
            return False

        before_sig = await self._page.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
                return JSON.stringify([location.href, links.length, links[0] || '', links[links.length - 1] || '']);
            }"""
        )

        try:
            await locator.scroll_into_view_if_needed(timeout=3000)
        except Exception:
            pass
        try:
            await locator.click(timeout=5000)
        except Exception:
            try:
                await locator.evaluate("el => el.click()")
            except Exception:
                return False

        try:
            await self._page.wait_for_function(
                """(prevSig) => {
                    const links = Array.from(document.querySelectorAll('a[href]')).map(a => a.href);
                    const nowSig = JSON.stringify([location.href, links.length, links[0] || '', links[links.length - 1] || '']);
                    return nowSig !== prevSig;
                }""",
                arg=before_sig,
                timeout=6000,
            )
        except Exception:
            pass

        await self._page.wait_for_timeout(self._scroll_pause_ms)
        return True
