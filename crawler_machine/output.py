from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OutputPath:
    """Representa a estrutura de diretórios e arquivos de uma execução."""

    base_dir: Path
    domain: str
    timestamp: str

    def prepare(self) -> None:
        """Cria a estrutura de diretórios no disco.

        Mantido como operação explícita para manter o objeto como
        valor puro até que a persistência real seja necessária.
        """
        self.root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        slug = _slugify_domain(self.domain)
        return self.base_dir / "runs" / slug / self.timestamp

    @property
    def discovered(self) -> Path:
        return self.root / "discovered.json"

    @property
    def schema(self) -> Path:
        return self.root / "schema.json"

    @property
    def raw(self) -> Path:
        return self.root / "raw.json"

    @property
    def normalized(self) -> Path:
        return self.root / "normalized.json"

    @property
    def errors(self) -> Path:
        return self.root / "errors.json"

    @property
    def rejected(self) -> Path:
        return self.root / "rejected.json"

    @property
    def quality_report(self) -> Path:
        return self.root / "quality_report.json"


def _slugify_domain(domain: str) -> str:
    """Converte um domínio em um slug seguro para nomes de pasta."""
    cleaned = re.sub(r"^https?://", "", domain.lower())
    cleaned = re.sub(r"[^a-z0-9.-]+", "-", cleaned)
    cleaned = re.sub(r"\.+$", "", cleaned)
    return cleaned.replace(".", "-")
