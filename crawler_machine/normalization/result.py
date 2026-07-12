from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NormalizationResult:
    """Resultado da normalização de um único campo.

    Attributes:
        value: valor normalizado, ou ``None`` se o campo for omitido.
        is_valid: ``True`` se o valor passou nas regras duras de validação.
        warnings: lista de problemas leves encontrados (ex: fora do catálogo).
        omitted: ``True`` se o campo deve ser removido do registro final.
    """

    value: Any
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    omitted: bool = False
