from __future__ import annotations

from typing import Any

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai.async_dispatcher import MemoryAdaptiveDispatcher

from crawler_machine.config import CrawlerConfig
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategies._constants import _DEFAULT_USER_AGENT


class Crawl4AIBrowser:
    """Adapter que isola a inicialização do AsyncWebCrawler do domínio."""

    def __init__(self, config: CrawlerConfig):
        self._config = config

    async def fetch(self, url: str) -> CrawlResult:
        """Executa fetch real usando Crawl4AI."""
        browser_config = BrowserConfig(
            headless=self._config.headless,
            viewport_width=1366,
            viewport_height=768,
            user_agent=self._config.user_agent or _DEFAULT_USER_AGENT,
            enable_stealth=self._config.enable_stealth,
        )
        crawler_config = CrawlerRunConfig(
            wait_for="css:body",
            wait_until=self._config.wait_until,
            page_timeout=self._config.page_timeout,
            remove_overlay_elements=True,
            cache_mode=self._resolve_cache_mode(self._config.cache_mode),
            mean_delay=self._config.mean_delay,
            max_range=self._config.max_range,
            simulate_user=True,
        )
        dispatcher = MemoryAdaptiveDispatcher(
            memory_threshold_percent=80.0,
            max_session_permit=self._config.max_concurrent,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(
                url=url,
                config=crawler_config,
                dispatcher=dispatcher,
            )

        if not result.success:
            return CrawlResult(
                url=result.url,
                success=False,
                data=[],
                error=result.error_message,
            )

        return CrawlResult(
            url=result.url,
            success=True,
            data=[],
            html=getattr(result, "html", None),
            images=self._extract_images(result),
        )

    @staticmethod
    def _resolve_cache_mode(mode: str | None) -> CacheMode:
        mapping = {
            "ENABLED": CacheMode.ENABLED,
            "BYPASS": CacheMode.BYPASS,
            "DISABLED": CacheMode.DISABLED,
            "READ_ONLY": CacheMode.READ_ONLY,
            "WRITE_ONLY": CacheMode.WRITE_ONLY,
        }
        return mapping.get((mode or "ENABLED").upper(), CacheMode.ENABLED)

    @staticmethod
    def _extract_images(result: Any) -> list[str]:
        """Extrai URLs de imagens do resultado do Crawl4AI."""
        images: list[str] = []
        media = getattr(result, "media", {}) or {}
        for image in media.get("images", []):
            if isinstance(image, str):
                images.append(image)
            elif isinstance(image, dict):
                src = image.get("src") or image.get("url")
                if src:
                    images.append(src)
        return images
