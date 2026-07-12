from __future__ import annotations

import logging

from crawler_machine.prospecting.filters import classify, dedup_by_domain
from crawler_machine.prospecting.models import (
    Candidate,
    CityTarget,
    Place,
    ProspectingResult,
    Summary,
)
from crawler_machine.prospecting.places import PlacesGateway
from crawler_machine.prospecting.repository import ProspectRepository

logger = logging.getLogger(__name__)


class Prospector:
    """Orquestra a descoberta de imobiliárias para uma lista de cidades.

    Para cada cidade, consulta o ``PlacesGateway``, classifica cada lugar
    em ``Candidate``, aplica dedup de domínio global e, opcionalmente,
    persiste os resultados via ``ProspectRepository``.
    """

    def __init__(
        self,
        cities: list[CityTarget],
        gateway: PlacesGateway,
        repository: ProspectRepository | None = None,
        run_id: str | None = None,
        max_per_city: int = 30,
        force: bool = False,
    ) -> None:
        self._cities = cities
        self._gateway = gateway
        self._repository = repository
        self._run_id = run_id
        self._max_per_city = max_per_city
        self._force = force

    def run(self) -> ProspectingResult:
        classified: list[Candidate] = []
        save_errors: list[str] = []

        for city in self._cities:
            places = self._gateway.search_imobiliarias(
                city.name, city.state, self._max_per_city
            )
            new_places = self._filter_new(places)
            city_classified = [classify(place) for place in new_places]
            classified.extend(city_classified)

            if self._repository is not None and self._run_id is not None:
                try:
                    self._repository.save_candidates(
                        city_classified, self._run_id
                    )
                except Exception as exc:  # noqa: BLE001
                    message = (
                        f"Falha ao salvar prospects para {city.label}: {exc}"
                    )
                    logger.error(message)
                    save_errors.append(message)

        classified = dedup_by_domain(classified)
        candidates = [c for c in classified if c.status == "candidate"]
        rejected = [c for c in classified if c.status == "rejected"]

        return ProspectingResult(
            query_cities=[city.label for city in self._cities],
            candidates=classified,
            summary=Summary(
                total=len(classified),
                candidates=len(candidates),
                rejected=len(rejected),
            ),
            save_errors=save_errors,
        )

    def _filter_new(self, places: list[Place]) -> list[Place]:
        if self._repository is None:
            return list(places)
        return self._repository.filter_new_places(places, force=self._force)
