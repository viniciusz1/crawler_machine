from __future__ import annotations

import asyncio
from typing import Any

from crawler_machine.discovery.items_catalog.browser import PlaywrightListingBrowser
from crawler_machine.discovery.items_catalog.models import ListingBrowser
from crawler_machine.discovery.items_catalog.paginator import CatalogPaginator
from crawler_machine.discovery.items_catalog.url_classifier import (
    URLClassifier,
    normalize_url,
)


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
        self._classifier = URLClassifier(listing_patterns=listing_patterns)
        self._paginator = CatalogPaginator(classifier=self._classifier)

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
                normalized_entry = normalize_url(entry_url)
                if normalized_entry in visited_pages:
                    continue

                await session.goto(entry_url)
                current_page_num = 1
                is_initial_entry = normalized_entry == normalize_url(base_url)

                while len(discovered) < max_urls and pages_visited < max_pages:
                    pages_visited += 1
                    scroll_links = await session.scroll_to_bottom()
                    snap = await session.snapshot()
                    visited_pages.add(normalize_url(snap.url))

                    if is_initial_entry and current_page_num == 1:
                        if self._classifier.is_property_url(snap.url, base_url, allow_entry=True):
                            normalized_self = normalize_url(snap.url)
                            if normalized_self not in seen_properties:
                                seen_properties.add(normalized_self)
                                discovered.append(normalized_self)

                    new_count = self._classifier.collect_property_urls(
                        snap.url,
                        [*snap.card_links, *snap.links, *scroll_links],
                        card_links=set(snap.card_links),
                        base_url=base_url,
                        include_subdomains=include_subdomains,
                        discovered=discovered,
                        seen=seen_properties,
                        max_urls=max_urls,
                    )

                    if (
                        is_initial_entry
                        and current_page_num == 1
                        and self._classifier.should_discover_entrypoints(snap.url, base_url)
                    ):
                        entrypoints = self._classifier.find_listing_entrypoints(
                            snap,
                            base_url=base_url,
                            visited_pages=visited_pages,
                            include_subdomains=include_subdomains,
                        )
                        for listing_url in entrypoints:
                            if listing_url not in queue:
                                queue.append(listing_url)

                        if entrypoints or self._classifier.is_property_url(
                            snap.url, base_url, allow_entry=True
                        ):
                            break

                    active_page = self._paginator.detect_active_page_number(
                        snap, current_page_num
                    )
                    action = self._paginator.detect_pagination_action(
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
