from __future__ import annotations

from typing import Any

from crawler_machine.prospecting.filters import classify, dedup_by_domain, root_domain
from crawler_machine.prospecting.places import PlacesGateway


class ProspectingExecutor:
    def __init__(self, gateway: PlacesGateway) -> None:
        self._gateway = gateway

    def run(
        self, plan: dict[str, Any], known_domains: set[str]
    ) -> list[dict[str, Any]]:
        places = self._gateway.search_imobiliarias(
            str(plan["city"]),
            str(plan["state"]),
            int(plan.get("max_results", 30)),
        )
        include_known = plan.get("requery_known_domains") is True
        filtered = [
            place
            for place in places
            if include_known
            or not place.website
            or root_domain(place.website) not in known_domains
        ]
        candidates = dedup_by_domain([classify(place) for place in filtered])

        return [
            {
                "root_domain": root_domain(candidate.base_url or "") or None,
                "google_place_id": candidate.google_place_id,
                "name": candidate.name,
                "city": candidate.city,
                "state": candidate.state,
                "base_url": candidate.base_url,
                "phone": candidate.phone,
                "address": candidate.address,
                "source": "google_places",
                "automatic_classification": candidate.status,
                "automatic_reason": candidate.reject_reason,
                "metadata": {"source": "google_places"},
            }
            for candidate in candidates
        ]
