from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CrawlResult:
    """Resultado de uma tentativa de extração de uma URL."""

    url: str
    success: bool
    data: list[dict[str, Any]]
    error: str | None = None
    images: list[str] = field(default_factory=list)
    html: str | None = None
