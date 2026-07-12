from __future__ import annotations

import asyncio
from typing import Any

from crawler_machine.pipeline.protocols import Sink
from crawler_machine.pipeline_helpers import detect_schema_type


class SchemaCache:
    """Camada de cache para schemas de extração."""

    def __init__(self, sink: Sink | None):
        self._sink = sink

    async def load(self, source_name: str, regenerate: bool) -> dict[str, Any] | None:
        if self._sink is None or regenerate:
            return None
        return await asyncio.to_thread(self._sink.load_latest_schema, source_name)

    async def save(
        self,
        source_name: str,
        schema: dict[str, Any],
        sample_url: str,
    ) -> int | None:
        if self._sink is None:
            return None

        schemas = schema.get("schemas", {})
        if not schemas:
            schema_type = detect_schema_type(schema)
            return await asyncio.to_thread(
                self._sink.save_schema_run,
                source_name,
                schema,
                schema_type,
                sample_url,
                [],
            )

        last_id: int | None = None
        for schema_type, schema_data in schemas.items():
            last_id = await asyncio.to_thread(
                self._sink.save_schema_run,
                source_name,
                schema_data,
                schema_type.upper(),
                sample_url,
                [],
            )
        return last_id
