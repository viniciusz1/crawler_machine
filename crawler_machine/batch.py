from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import yaml

from crawler_machine.config import DomainConfig
from crawler_machine.output import OutputPath
from crawler_machine.pipeline import build_pipeline
from crawler_machine.sink import RunStore


class BatchError(Exception):
    """Erro ao processar um batch de imobiliárias."""


Runner = Callable[[str, str, str | None], dict[str, Any]]


def build_default_runner(
    config: DomainConfig,
    output_dir: Path,
    verbose: bool = False,
    sink: RunStore | None = None,
) -> Runner:
    """Constrói o runner padrão que executa o pipeline completo."""

    def runner(
        base_url: str, source_name: str, sample_url: str | None
    ) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output = OutputPath(
            base_dir=output_dir, domain=base_url, timestamp=timestamp
        )

        pipeline = build_pipeline(
            config=config,
            output=output,
            source_name=source_name,
            sink=sink,
            verbose=verbose,
        )

        result = pipeline.run_sync(base_url, sample_url=sample_url)

        return {
            "status": "success",
            "normalized_count": len(result.normalized),
            "error_count": len(result.errors),
            "run_id": result.run_id,
            "output_dir": str(output.root),
        }

    return runner


def _noop_runner(
    base_url: str, source_name: str, sample_url: str | None
) -> dict[str, Any]:
    """Runner placeholder usado quando nenhum runner é fornecido."""
    raise RuntimeError("nenhum runner foi configurado")


def run_batch(
    yaml_path: Path,
    output_dir: Path,
    runner: Runner | None = None,
) -> dict[str, Any]:
    """Processa um batch de imobiliárias a partir de um arquivo YAML.

    Cada item do YAML deve conter ``base_url`` e ``source_name``. O campo
    ``sample_url`` é opcional quando já existe schema/discovery cacheado.
    """
    runner = runner or _noop_runner
    raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if not raw or not isinstance(raw, list):
        raise BatchError("lista de imobiliárias está vazia")

    parsed: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in raw:
        for field in ("base_url", "source_name"):
            if not entry.get(field):
                raise BatchError(f"campo obrigatório ausente: {field}")

        source_name = entry["source_name"]
        if source_name in seen:
            raise BatchError(f"source_name duplicado: {source_name}")
        seen.add(source_name)

        parsed.append(
            {
                "base_url": entry["base_url"],
                "source_name": source_name,
                "sample_url": entry.get("sample_url"),
            }
        )

    items: list[dict[str, Any]] = []
    for entry in parsed:
        try:
            result = runner(
                entry["base_url"], entry["source_name"], entry["sample_url"]
            )
        except Exception as exc:  # noqa: BLE001
            result = {
                "status": "failed",
                "error_message": str(exc),
            }

        items.append(
            {
                "source_name": entry["source_name"],
                "base_url": entry["base_url"],
                "sample_url": entry["sample_url"],
                "status": result.get("status"),
                "run_id": result.get("run_id"),
                "normalized_count": result.get("normalized_count"),
                "error_count": result.get("error_count"),
                "output_dir": result.get("output_dir"),
                "error_message": result.get("error_message"),
            }
        )

    succeeded = sum(1 for item in items if item["status"] == "success")
    failed = len(items) - succeeded

    report = {
        "metadata": {
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "total": len(items),
            "succeeded": succeeded,
            "failed": failed,
        },
        "items": items,
    }

    reports_dir = output_dir / "batch-reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    report_path = reports_dir / f"{timestamp}.json"
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return report
