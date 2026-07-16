from __future__ import annotations

from typing import Any

from crawler_machine.config import FieldConfig, LLMConfig
from crawler_machine.prospecting.home_sample_finder import HomeSampleFinder
from crawler_machine.prospecting.models import Candidate
from crawler_machine.schema_generator import SchemaGenerator


class HomeSampleFinderAdapter:
    def __init__(self, finder: HomeSampleFinder | None = None) -> None:
        self._finder = finder or HomeSampleFinder()

    def find(self, base_url: str) -> str | None:
        return self._finder.find(
            Candidate(
                city="",
                state="",
                name=base_url,
                base_url=base_url,
                source_name=None,
            )
        )


class ExtractionProfileGenerator:
    def __init__(self, llm_config: LLMConfig) -> None:
        self._llm_config = llm_config

    def generate(
        self, sample_url: str, fields: list[dict[str, Any]]
    ) -> dict[str, Any]:
        generator = SchemaGenerator(
            llm_config=self._llm_config,
            fields=[
                FieldConfig(
                    name=str(field["name"]),
                    description=str(field.get("description", field["name"])),
                    coerce=None,
                )
                for field in fields
            ],
        )
        generated = generator.generate_sync(sample_url)
        schemas = generated["schemas"]
        return {
            "schemas": schemas,
            "strategies": list(schemas.keys()),
            "fields": fields,
            "parameters": generated["metadata"],
        }
