"""Versioned extraction observations; persistence stays at the worker boundary."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True)
class DiagnosticEvent:
    """One immutable observation, with a stable identity for delivery retries."""

    kind: str
    stage: str
    outcome: str
    url: str | None = None
    strategy: str | None = None
    duration_ms: int = 0
    error_code: str | None = None
    message: str | None = None
    fields_present: tuple[str, ...] = ()
    fields_missing: tuple[str, ...] = ()
    fallback: bool = False
    event_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: int = field(default=1, init=False)


DiagnosticObserver = Callable[[DiagnosticEvent], None]


def safe_message(message: str | None) -> str | None:
    """Bound error evidence and remove common credential representations."""
    if message is None:
        return None
    message = re.sub(r"(?i)(bearer\s+)[^\s,;]+", r"\1[redacted]", message)
    return re.sub(
        r"(?i)((?:api[_-]?key|password|token|secret)[\"']?\s*[:=]\s*[\"']?)[^\s\"'&,;]+",
        r"\1[redacted]",
        message,
    )[:2000]


def observe(observer: DiagnosticObserver | None, event: DiagnosticEvent) -> None:
    """Deliver an observation without making the engine depend on a database."""
    if observer is not None:
        observer(event)
