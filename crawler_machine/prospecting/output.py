from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import yaml

from crawler_machine.prospecting.models import ProspectingResult


def write_candidates(
    result: ProspectingResult,
    path: Path,
    fmt: str = "yaml",
    generated_at: str | None = None,
) -> Path:
    """Serializa o resultado da prospecção em YAML ou JSON.

    O arquivo é de **revisão humana**: o operador remove os ``rejected``,
    preenche ``sample_url`` e cola os ``candidate`` no YAML do
    ``clone-das-sombras``.
    """
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()

    document = {
        "generated_at": generated_at,
        "query_cities": result.query_cities,
        "candidates": [candidate.to_dict() for candidate in result.candidates],
        "summary": asdict(result.summary),
    }

    path.parent.mkdir(parents=True, exist_ok=True)

    if fmt == "yaml":
        path.write_text(
            yaml.safe_dump(document, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    elif fmt == "json":
        path.write_text(
            json.dumps(document, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    else:
        raise ValueError(f"formato não suportado: {fmt}")

    return path
