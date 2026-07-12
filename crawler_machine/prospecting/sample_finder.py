from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Callable

import httpx

from crawler_machine.prospecting.places import HttpResponse


class SearchError(Exception):
    """Erro ao consultar a Google Custom Search API."""


Requester = Callable[[str, dict[str, str], dict[str, Any]], HttpResponse]


class SearchGateway(ABC):
    """Contrato para fontes de busca de URLs de imóveis por query."""

    @abstractmethod
    def search(self, query: str, num_results: int = 5) -> list[str]:
        """Busca URLs para a query, até ``num_results`` resultados."""


class GoogleCustomSearchGateway(SearchGateway):
    """Gateway para a Google Custom Search API.

    Usa ``httpx`` para consultar ``https://www.googleapis.com/customsearch/v1``
    com os parâmetros ``key``, ``cx``, ``q`` e ``num``. O ``requester`` é
    injetável para testes sem rede.
    """

    BASE_URL = "https://www.googleapis.com/customsearch/v1"
    DEFAULT_TIMEOUT = 30.0
    _RETRY_DELAYS = [1.0, 2.0]

    def __init__(
        self,
        api_key: str,
        cx: str,
        requester: Requester | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key:
            raise SearchError("GOOGLE_CUSTOM_SEARCH_KEY não definida")
        if not cx:
            raise SearchError("GOOGLE_CUSTOM_SEARCH_CX não definida")
        self._api_key = api_key
        self._cx = cx
        self._requester = requester or self._build_default_requester()
        self._sleep = sleep

    @staticmethod
    def _build_default_requester() -> Requester:
        client = httpx.Client(timeout=GoogleCustomSearchGateway.DEFAULT_TIMEOUT)

        def requester(
            url: str, headers: dict[str, str], params: dict[str, Any]
        ) -> HttpResponse:
            response = client.get(url, headers=headers, params=params)
            return HttpResponse(response.status_code, response.json())

        return requester

    def search(self, query: str, num_results: int = 5) -> list[str]:
        params = {
            "key": self._api_key,
            "cx": self._cx,
            "q": query,
            "num": num_results,
        }
        headers: dict[str, str] = {}

        response = self._execute_request(headers, params)
        if response.status_code >= 400:
            raise SearchError(
                f"Custom Search API retornou {response.status_code}: "
                f"{self._error_message(response.payload)}"
            )

        payload = response.payload or {}
        items = payload.get("items", [])
        return [item["link"] for item in items if item.get("link")][:num_results]

    def _execute_request(
        self, headers: dict[str, str], params: dict[str, Any]
    ) -> HttpResponse:
        attempt = 0
        max_attempts = len(self._RETRY_DELAYS) + 1
        while attempt < max_attempts:
            try:
                return self._requester(self.BASE_URL, headers, params)
            except TimeoutError:
                if attempt >= len(self._RETRY_DELAYS):
                    raise SearchError(
                        f"Custom Search API timeout após {max_attempts} tentativas"
                    ) from None
                self._sleep(self._RETRY_DELAYS[attempt])
                attempt += 1

        raise SearchError("Custom Search API resposta inesperada")

    @staticmethod
    def _error_message(payload: dict[str, Any]) -> str:
        error = payload.get("error") or {}
        return error.get("message") or str(payload)
