from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Callable

from crawler_machine.discovery.items_catalog.dom_parser import parse_page_snapshot
from crawler_machine.discovery.items_catalog.models import (
    ListingBrowserSession,
    PageControl,
    PageSnapshot,
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
