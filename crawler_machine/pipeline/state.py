from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crawler_machine.extermination.exterminator import RejectedRecord
from crawler_machine.output import OutputPath


@dataclass(frozen=True)
class PipelineResult:
    normalized: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    output: OutputPath
    rejected: list[RejectedRecord] = field(default_factory=list)
    run_id: int | None = None


@dataclass
class ExecutionState:
    """Estado intermediário de uma execução do pipeline."""

    urls: list[str]
    schema: dict[str, Any]
    raw_data: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    survivors: list[dict[str, Any]]
    rejected: list[RejectedRecord]
    normalized: list[dict[str, Any]]
    quality_report: dict[str, Any]
    discovery_run_id: int | None = None
    schema_run_id: int | None = None
