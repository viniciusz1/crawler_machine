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


from dataclasses import dataclass

from crawler_machine.prospecting.models import Candidate


@dataclass(frozen=True)
class EnrichedCandidate:
    """Candidato enriquecido com uma ``sample_url`` descoberta."""

    base_url: str
    source_name: str
    sample_url: str | None


class SampleEnricher:
    """Enriquece candidatos com ``sample_url`` via busca por tipo de imóvel.

    Para cada candidato, tenta uma cadeia de queries:
      - tipos: apartamento → geminado → casa
      - variações: com cidade/UF → sem cidade/UF → com "venda"

    A primeira URL retornada que não seja a home do site vira ``sample_url``.
    Se nada for encontrado, o candidato é emitido com ``sample_url: None``.
    """

    _PROPERTY_TYPES = ["apartamento", "geminado", "casa"]
    _DEFAULT_NUM_RESULTS = 5

    def __init__(
        self,
        gateway: SearchGateway,
        sleep: Callable[[float], None] = time.sleep,
        delay: float = 1.0,
    ) -> None:
        self._gateway = gateway
        self._sleep = sleep
        self._delay = delay

    def enrich(self, candidates: list[Candidate]) -> list[EnrichedCandidate]:
        """Enriquece a lista de candidatos com ``sample_url``."""
        self._ensure_unique_source_names(candidates)

        enriched: list[EnrichedCandidate] = []
        for candidate in candidates:
            sample_url = self._find_sample(candidate)
            enriched.append(
                EnrichedCandidate(
                    base_url=candidate.base_url or "",
                    source_name=candidate.source_name or "",
                    sample_url=sample_url,
                )
            )
        return enriched

    @staticmethod
    def _ensure_unique_source_names(candidates: list[Candidate]) -> None:
        seen: set[str] = set()
        for candidate in candidates:
            source_name = candidate.source_name or ""
            if source_name in seen:
                raise ValueError(f"source_name duplicado: {source_name}")
            seen.add(source_name)

    def _find_sample(self, candidate: Candidate) -> str | None:
        base_url = candidate.base_url or ""
        city = candidate.city
        state = candidate.state

        for property_type in self._PROPERTY_TYPES:
            for query in self.build_queries(base_url, property_type, city, state):
                urls = self._gateway.search(query, num_results=self._DEFAULT_NUM_RESULTS)
                self._sleep(self._delay)
                for url in urls:
                    if url.rstrip("/") != base_url.rstrip("/"):
                        return url
        return None

    @staticmethod
    def build_queries(
        base_url: str, property_type: str, city: str, state: str
    ) -> list[str]:
        return [
            f'site:{base_url} "{property_type}" "{city}" "{state}"',
            f'site:{base_url} "{property_type}"',
            f'site:{base_url} "{property_type}" "venda"',
        ]
