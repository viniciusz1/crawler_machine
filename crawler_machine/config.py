from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key_env: str


@dataclass(frozen=True)
class CrawlerConfig:
    page_timeout: int
    max_concurrent: int
    chunk_size: int
    chunk_delay: float
    headless: bool
    wait_until: str = "domcontentloaded"
    enable_stealth: bool = True
    cache_mode: str = "ENABLED"
    mean_delay: float = 0.5
    max_range: float = 1.0
    retry_attempts: int = 3
    retry_base_delay: float = 2.0
    user_agent: str | None = None
    enable_fit_markdown_regex: bool = True
    enable_fit_markdown_llm: bool = False
    enable_llm_fallback: bool = False


@dataclass(frozen=True)
class DiscoveryConfig:
    max_urls: int
    listing_patterns: list[str] | None = None


@dataclass(frozen=True)
class FieldConfig:
    name: str
    description: str
    coerce: str | None = None


@dataclass(frozen=True)
class DomainConfig:
    llm: LLMConfig
    crawler: CrawlerConfig
    discovery: DiscoveryConfig
    fields: list[FieldConfig]


class ConfigLoader:
    """Carrega a configuração global do domínio a partir de um arquivo JSON."""

    @staticmethod
    def load(path: Path) -> DomainConfig:
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, Any] = json.load(f)

        crawler_data = data["crawler"]
        discovery_data = data["discovery"]

        return DomainConfig(
            llm=LLMConfig(
                provider=data["llm"]["provider"],
                base_url=data["llm"]["base_url"],
                api_key_env=data["llm"]["api_key_env"],
            ),
            crawler=CrawlerConfig(
                page_timeout=crawler_data["page_timeout"],
                max_concurrent=crawler_data["max_concurrent"],
                chunk_size=crawler_data["chunk_size"],
                chunk_delay=crawler_data["chunk_delay"],
                headless=crawler_data["headless"],
                wait_until=crawler_data.get("wait_until", "domcontentloaded"),
                enable_stealth=crawler_data.get("enable_stealth", True),
                cache_mode=crawler_data.get("cache_mode", "ENABLED"),
                mean_delay=crawler_data.get("mean_delay", 0.5),
                max_range=crawler_data.get("max_range", 1.0),
                retry_attempts=crawler_data.get("retry_attempts", 3),
                retry_base_delay=crawler_data.get("retry_base_delay", 2.0),
                user_agent=crawler_data.get("user_agent"),
                enable_fit_markdown_regex=crawler_data.get(
                    "enable_fit_markdown_regex", True
                ),
                enable_fit_markdown_llm=crawler_data.get(
                    "enable_fit_markdown_llm", False
                ),
                enable_llm_fallback=crawler_data.get("enable_llm_fallback", False),
            ),
            discovery=DiscoveryConfig(
                max_urls=discovery_data["max_urls"],
                listing_patterns=discovery_data.get("listing_patterns"),
            ),
            fields=[
                FieldConfig(
                    name=field["name"],
                    description=field["description"],
                    coerce=field.get("coerce"),
                )
                for field in data["fields"]
            ],
        )
