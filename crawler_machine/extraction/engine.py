from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any, Protocol

from crawler_machine.diagnostics import (
    DiagnosticEvent,
    DiagnosticObserver,
    observe,
    safe_message,
)
from crawler_machine.config import CrawlerConfig
from crawler_machine.config import REQUIRED_FIELDS as REQUIRED_FIELDS
from crawler_machine.extraction.result import CrawlResult
from crawler_machine.extraction.strategy import ExtractionStrategy
from crawler_machine.extraction.strategies.http_runner import HttpRunner

logger = logging.getLogger(__name__)

CrawlOutcome = tuple[dict[str, Any] | None, dict[str, Any] | None]


class HtmlCollector(Protocol):
    async def run_many(self, urls: list[str]) -> list[CrawlResult]: ...


class CrawlEngine:
    """Orquestra a cadeia de fallback de extração sobre uma lista de URLs."""

    def __init__(
        self,
        config: CrawlerConfig,
        required_fields: set[str] | tuple[str, ...],
        strategies: list[ExtractionStrategy],
        html_collector: HtmlCollector | None = None,
    ):
        self._config = config
        self._required_fields = set(required_fields)
        self._strategies = [s for s in strategies if s.enabled]
        self._html_collector = html_collector or HttpRunner(config)

    async def crawl(
        self,
        urls: list[str],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa a cadeia de fallback para cada URL."""
        outcomes = await self.crawl_many(urls)
        data: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []

        for result, error in outcomes:
            if error is not None:
                errors.append(error)
            if result is not None:
                data.append(result)

        return data, errors

    async def crawl_many(
        self, urls: list[str], on_diagnostic: DiagnosticObserver | None = None
    ) -> list[CrawlOutcome]:
        """Executa o crawl em lotes e preserva um resultado por URL."""
        if not urls:
            return []

        outcomes: list[CrawlOutcome] = []
        extraction_limit = asyncio.Semaphore(max(1, self._config.max_concurrent))

        for index, chunk in enumerate(self._chunks(urls, self._config.chunk_size)):
            if index > 0 and self._config.chunk_delay > 0:
                await asyncio.sleep(self._config.chunk_delay)

            fetch_started = perf_counter()
            try:
                fetched_results = await self._html_collector.run_many(chunk)
            except Exception as exc:  # pragma: no cover - adapter safety net
                logger.exception("Batch HTML collection failed")
                outcomes.extend(
                    self._fetch_failure(url, str(exc), on_diagnostic) for url in chunk
                )
                continue

            if len(fetched_results) != len(chunk):
                error = "Batch HTML collection returned an invalid result count"
                outcomes.extend(
                    self._fetch_failure(url, error, on_diagnostic) for url in chunk
                )
                continue

            observe(
                on_diagnostic,
                DiagnosticEvent(
                    kind="stage",
                    stage="fetch",
                    outcome="completed",
                    duration_ms=round((perf_counter() - fetch_started) * 1000),
                ),
            )
            chunk_outcomes = await asyncio.gather(
                *(
                    self._extract_with_limit(
                        extraction_limit,
                        url,
                        fetched,
                        on_diagnostic,
                    )
                    for url, fetched in zip(chunk, fetched_results, strict=True)
                )
            )
            outcomes.extend(chunk_outcomes)

        return outcomes

    def crawl_sync(
        self, urls: list[str]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Versão síncrona de ``crawl``."""
        return asyncio.run(self.crawl(urls))

    def crawl_many_sync(
        self, urls: list[str], on_diagnostic: DiagnosticObserver | None = None
    ) -> list[CrawlOutcome]:
        """Versão síncrona de ``crawl_many``."""
        return asyncio.run(self.crawl_many(urls, on_diagnostic=on_diagnostic))

    async def _extract_with_limit(
        self,
        semaphore: asyncio.Semaphore,
        url: str,
        fetched: CrawlResult,
        on_diagnostic: DiagnosticObserver | None = None,
    ) -> CrawlOutcome:
        async with semaphore:
            outcome = await self._extract_fetched(url, fetched, on_diagnostic)
            record, error = outcome
            present = tuple(
                sorted(
                    key
                    for key, value in (record or {}).items()
                    if not key.startswith("_") and self._is_meaningful(value)
                )
            )
            observe(
                on_diagnostic,
                DiagnosticEvent(
                    kind="extraction_completed",
                    stage="extraction",
                    outcome="succeeded" if record is not None else "failed",
                    url=url,
                    error_code="extraction_failed" if error else None,
                    fields_present=present,
                    fields_missing=tuple(sorted(self._required_fields - set(present))),
                ),
            )
            return outcome

    async def _extract_fetched(
        self,
        url: str,
        fetched: CrawlResult,
        on_diagnostic: DiagnosticObserver | None = None,
    ) -> CrawlOutcome:
        """Executa a cadeia de fallback sobre HTML já coletado."""
        if not fetched.success:
            return self._fetch_failure(
                url,
                fetched.error or "HTML collection failed",
                on_diagnostic,
                terminal=False,
            )
        if not fetched.html:
            return self._fetch_failure(
                url, "HTML collection returned no HTML", on_diagnostic, terminal=False
            )

        accumulated: dict[str, Any] = {}
        trace: dict[str, str] = {}
        last_error: str | None = None

        if "url" in self._required_fields:
            accumulated["url"] = url
            trace["url"] = "url"

        for strategy_index, strategy in enumerate(self._strategies):
            attempt_started = perf_counter()
            before = set(accumulated)
            previous = CrawlResult(
                url=fetched.url,
                success=True,
                data=[dict(accumulated)] if accumulated else [],
                html=fetched.html,
                images=fetched.images,
            )
            try:
                result = await strategy.extract(url, previous)
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("Strategy %s failed for %s", strategy.name, url)
                last_error = str(exc)
                observe(
                    on_diagnostic,
                    DiagnosticEvent(
                        kind="attempt",
                        stage="extraction",
                        outcome="failed",
                        url=url,
                        strategy=strategy.name,
                        duration_ms=round((perf_counter() - attempt_started) * 1000),
                        error_code="strategy_exception",
                        message=safe_message(last_error),
                        fallback=strategy_index > 0,
                    ),
                )
                continue

            if not result.success:
                last_error = result.error or f"{strategy.name} failed"
                observe(
                    on_diagnostic,
                    DiagnosticEvent(
                        kind="attempt",
                        stage="extraction",
                        outcome="failed",
                        url=url,
                        strategy=strategy.name,
                        duration_ms=round((perf_counter() - attempt_started) * 1000),
                        error_code="strategy_failed",
                        message=safe_message(last_error),
                        fallback=strategy_index > 0,
                    ),
                )
                continue

            for record in result.data:
                if isinstance(record, dict):
                    for key, value in record.items():
                        if key not in accumulated and self._is_meaningful(value):
                            accumulated[key] = value
                            trace[key] = strategy.name

            present_fields = {
                key for key, value in accumulated.items() if self._is_meaningful(value)
            }
            provided = tuple(sorted(set(accumulated) - before))
            observe(
                on_diagnostic,
                DiagnosticEvent(
                    kind="attempt",
                    stage="extraction",
                    outcome="succeeded" if provided else "no_contribution",
                    url=url,
                    strategy=strategy.name,
                    duration_ms=round((perf_counter() - attempt_started) * 1000),
                    fields_present=provided,
                    fields_missing=tuple(
                        sorted(self._required_fields - present_fields)
                    ),
                    fallback=strategy_index > 0,
                ),
            )
            if self._required_fields.issubset(present_fields):
                break

        if not accumulated or (
            set(accumulated.keys()) == {"url"} and last_error is not None
        ):
            return None, {"url": url, "error": last_error or "no data extracted"}

        accumulated["_extraction_trace"] = trace
        return accumulated, None

    def _fetch_failure(
        self,
        url: str,
        error: str,
        observer: DiagnosticObserver | None,
        terminal: bool = True,
    ) -> CrawlOutcome:
        observe(
            observer,
            DiagnosticEvent(
                kind="fetch",
                stage="fetch",
                outcome="failed",
                url=url,
                error_code="fetch_failed",
                message=safe_message(error),
            ),
        )
        if terminal:
            observe(
                observer,
                DiagnosticEvent(
                    kind="extraction_completed",
                    stage="extraction",
                    outcome="failed",
                    url=url,
                    error_code="fetch_failed",
                    fields_missing=tuple(sorted(self._required_fields)),
                ),
            )
        return None, {"url": url, "error": error}

    @staticmethod
    def _is_meaningful(value: Any) -> bool:
        """Verifica se um valor extraído deve ser considerado presente."""
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
        if isinstance(value, (list, dict)) and not value:
            return False
        return True

    @staticmethod
    def _chunks(items: list[str], size: int) -> list[list[str]]:
        """Divide uma lista em lotes de tamanho máximo ``size``."""
        if size <= 0:
            return [items]
        return [items[i : i + size] for i in range(0, len(items), size)]
