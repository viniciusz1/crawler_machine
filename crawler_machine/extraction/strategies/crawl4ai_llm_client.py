from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from crawl4ai.extraction_strategy import LLMExtractionStrategy

from crawler_machine.config import LLMConfig

logger = logging.getLogger(__name__)


class Crawl4AILlmClient:
    """Adapter que isola a chamada ao LLM do Crawl4AI."""

    def __init__(self, llm_config: LLMConfig):
        self._llm_config = llm_config

    async def extract(
        self,
        url: str,
        html: str,
        instruction: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Executa o LLM sobre HTML já coletado, sem abrir outro navegador."""
        api_key = os.environ.get(self._llm_config.api_key_env, "")
        extraction_strategy = LLMExtractionStrategy(
            provider=self._llm_config.provider,
            api_token=api_key,
            base_url=self._llm_config.base_url,
            instruction=instruction,
            schema=schema,
            extraction_type="schema",
        )
        records = await asyncio.to_thread(extraction_strategy.run, url, [html])
        valid_records = [
            record
            for record in records
            if isinstance(record, dict) and record.get("error") is not True
        ]
        if not valid_records:
            raise RuntimeError("LLM extraction returned no valid record")

        allowed_fields = set(schema.get("properties", {}))
        merged: dict[str, Any] = {}
        for record in valid_records:
            for key, value in record.items():
                if key in allowed_fields and key not in merged and value is not None:
                    merged[key] = value
        return merged
