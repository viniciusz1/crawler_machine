from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Callable

from crawler_machine.prospecting.models import Place


class PlacesError(Exception):
    """Erro ao consultar a Google Places API."""


@dataclass(frozen=True)
class HttpResponse:
    """Resposta de uma chamada HTTP, já com o payload parseado."""

    status_code: int
    payload: dict[str, Any]


Requester = Callable[[str, dict[str, str], dict[str, Any]], HttpResponse]


class PlacesGateway(ABC):
    """Contrato para fontes de descoberta de imobiliárias por cidade."""

    @abstractmethod
    def search_imobiliarias(
        self, city: str, state: str, max_results: int
    ) -> list[Place]:
        """Busca imobiliárias para a cidade/UF, até ``max_results`` resultados."""


class GooglePlacesGateway(PlacesGateway):
    """Gateway para a Google Places API v1 (``places:searchText``).

    Usa ``X-Goog-FieldMask`` para solicitar ``websiteUri`` já no text search,
    evitando uma chamada de Place Details por candidato. Pagina via
    ``nextPageToken``. O ``requester`` é injetável para testes sem rede.
    """

    BASE_URL = "https://places.googleapis.com/v1/places:searchText"
    FIELD_MASK = (
        "places.id,"
        "places.displayName,"
        "places.websiteUri,"
        "places.formattedAddress,"
        "places.internationalPhoneNumber,"
        "nextPageToken"
    )

    def __init__(
        self,
        api_key: str,
        requester: Requester | None = None,
        sleep: Callable[[float], None] = time.sleep,
        page_delay: float = 2.0,
    ) -> None:
        if not api_key:
            raise PlacesError("GOOGLE_PLACES_API_KEY não definida")
        self._api_key = api_key
        self._requester = requester or self._build_default_requester()
        self._sleep = sleep
        self._page_delay = page_delay

    @staticmethod
    def _build_default_requester() -> Requester:
        import httpx

        client = httpx.Client(timeout=30.0)

        def requester(
            url: str, headers: dict[str, str], body: dict[str, Any]
        ) -> HttpResponse:
            response = client.post(url, headers=headers, json=body)
            return HttpResponse(response.status_code, response.json())

        return requester

    def search_imobiliarias(
        self, city: str, state: str, max_results: int
    ) -> list[Place]:
        query = f"imobiliária em {city} {state}"
        places: list[Place] = []
        page_token: str | None = None

        while len(places) < max_results:
            body: dict[str, Any] = {"textQuery": query, "languageCode": "pt-BR"}
            if page_token:
                body["pageToken"] = page_token

            headers = {
                "X-Goog-Api-Key": self._api_key,
                "X-Goog-FieldMask": self.FIELD_MASK,
                "Content-Type": "application/json",
            }
            response = self._requester(self.BASE_URL, headers, body)
            if response.status_code >= 400:
                raise PlacesError(
                    f"Places API retornou {response.status_code}: "
                    f"{self._error_message(response.payload)}"
                )

            payload = response.payload or {}
            for raw in payload.get("places", []):
                place = self._parse_place(raw, city, state)
                if place is not None:
                    places.append(place)
                    if len(places) >= max_results:
                        break

            page_token = payload.get("nextPageToken")
            if not page_token or len(places) >= max_results:
                break
            self._sleep(self._page_delay)

        return places[:max_results]

    @staticmethod
    def _parse_place(raw: dict[str, Any], city: str, state: str) -> Place | None:
        place_id = raw.get("id")
        if not place_id:
            return None
        display_name = raw.get("displayName") or {}
        return Place(
            place_id=place_id,
            name=display_name.get("text") or "",
            website=raw.get("websiteUri"),
            phone=raw.get("internationalPhoneNumber"),
            address=raw.get("formattedAddress"),
            city=city,
            state=state,
        )

    @staticmethod
    def _error_message(payload: dict[str, Any]) -> str:
        error = payload.get("error") or {}
        return error.get("message") or str(payload)
