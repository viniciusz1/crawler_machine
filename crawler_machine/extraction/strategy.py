from __future__ import annotations

from typing import Any, Protocol

from crawler_machine.extraction.result import CrawlResult


class ExtractionStrategy(Protocol):
    """Contrato para estratégias de extração da cadeia de fallback."""

    name: str
    enabled: bool

    async def extract(self, url: str, previous: CrawlResult | None) -> CrawlResult:
        """Extrai dados de uma URL, preenchendo apenas campos faltantes.

        Recebe o resultado acumulado das estratégias anteriores (``previous``)
        e deve retornar um novo ``CrawlResult`` com os campos complementares.
        O HTML bruto, quando disponível em ``previous.html``, deve ser
        reaproveitado para evitar requests repetidos.
        """
        ...


class StrategyResult:
    """Helper para construir resultados parciais dentro de uma estratégia."""

    def __init__(
        self,
        url: str,
        data: list[dict[str, Any]] | None = None,
        html: str | None = None,
        images: list[str] | None = None,
        error: str | None = None,
        success: bool = True,
    ):
        self.url = url
        self.data = data or []
        self.html = html
        self.images = images or []
        self.error = error
        self.success = success

    def to_crawl_result(self) -> CrawlResult:
        return CrawlResult(
            url=self.url,
            success=self.success,
            data=self.data,
            error=self.error,
            images=self.images,
            html=self.html,
        )
