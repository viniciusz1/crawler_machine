from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class RejectedRecord:
    """Registro rejeitado pelo Exterminator, com metadados de auditoria."""

    index: int
    record: dict[str, Any]
    missing_fields: list[str]

    @property
    def reason(self) -> str:
        return f"missing required fields: {', '.join(self.missing_fields)}"


class Exterminator:
    """Filtra registros brutos do crawler que não contenham campos obrigatórios mínimos.

    Executa antes da normalização. Registros que falharem na presença mínima são
    removidos do fluxo principal e devolvidos como rejeitados para auditoria.
    """

    DEFAULT_REQUIRED_FIELDS = [
        "bairro",
        "cidade",
        "valor",
        "tipo_imovel",
        "url",
        "imagem",
    ]

    def __init__(self, required_fields: list[str] | None = None):
        self.required_fields = required_fields or list(self.DEFAULT_REQUIRED_FIELDS)

    def filter(
        self,
        records: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[RejectedRecord]]:
        """Separa registros válidos (presença mínima) de rejeitados."""
        survivors: list[dict[str, Any]] = []
        rejected: list[RejectedRecord] = []

        for index, record in enumerate(records):
            missing = self._missing_fields(record)
            if missing:
                rejected.append(
                    RejectedRecord(
                        index=index,
                        record=record,
                        missing_fields=missing,
                    )
                )
            else:
                survivors.append(record)

        return survivors, rejected

    def _missing_fields(self, record: dict[str, Any]) -> list[str]:
        return [
            field
            for field in self.required_fields
            if field not in record or self._is_empty(record[field])
        ]

    @staticmethod
    def _is_empty(value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        if isinstance(value, list):
            return len(value) == 0 or all(Exterminator._is_empty(item) for item in value)
        if isinstance(value, dict) and len(value) == 0:
            return True
        return False
