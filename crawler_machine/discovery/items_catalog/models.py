from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator, Protocol


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
