from __future__ import annotations

from typing import Any

from crawler_machine.config import DomainConfig, FieldConfig, LLMConfig
from crawler_machine.extraction.factory import build_crawl_engine
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
        self,
        sample_url: str,
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
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
        strategies = (
            list(extraction_policy["strategies"])
            if extraction_policy is not None
            else list(schemas.keys())
        )
        parameters = dict(generated["metadata"])
        if extraction_policy is not None:
            parameters["extraction_policy"] = dict(extraction_policy)
        return {
            "schemas": schemas,
            "strategies": strategies,
            "fields": fields,
            "parameters": parameters,
        }


class ConfiguredProfileExtractor:
    def __init__(self, config: DomainConfig) -> None:
        self._config = config

    def extract(
        self,
        url: str,
        schemas: dict[str, Any],
        fields: list[dict[str, Any]],
        extraction_policy: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any] | None, list[str]]:
        field_config = [
            FieldConfig(
                name=str(field["name"]),
                description=str(field.get("description", field["name"])),
                coerce=field.get("coerce"),
            )
            for field in fields
        ]
        operation_config = DomainConfig(
            llm=self._config.llm,
            crawler=self._config.crawler,
            discovery=self._config.discovery,
            fields=field_config,
        )
        required_fields = {
            str(field["name"]) for field in fields if field.get("required") is True
        }
        engine = build_crawl_engine(
            operation_config,
            {"schemas": schemas},
            required_fields=required_fields,
            extraction_policy=extraction_policy,
        )
        records, errors = engine.crawl_sync([url])
        return (
            records[0] if records else None,
            [str(error.get("error", "extraction failed")) for error in errors],
        )
