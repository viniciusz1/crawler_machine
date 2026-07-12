from __future__ import annotations

import asyncio

from crawler_machine.pipeline.protocols import Sink


class DiscoveryCache:
    """Camada de cache para resultados de discovery."""

    def __init__(self, sink: Sink | None):
        self._sink = sink

    async def load(self, source_name: str, regenerate: bool) -> list[str] | None:
        if self._sink is None or regenerate:
            return None
        return await asyncio.to_thread(
            self._sink.load_latest_discovery, source_name
        )

    async def save(self, source_name: str, urls: list[str]) -> int | None:
        if self._sink is None:
            return None
        return await asyncio.to_thread(
            self._sink.save_discovery_run, source_name, urls
        )
