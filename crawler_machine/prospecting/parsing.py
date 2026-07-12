from __future__ import annotations

from crawler_machine.prospecting.models import CityTarget


class CityParseError(ValueError):
    """Erro ao interpretar a lista de cidades informada pelo operador."""


def parse_cities(raw: str) -> list[CityTarget]:
    """Interpreta ``"Cidade,UF;Cidade,UF"`` em uma lista de ``CityTarget``.

    A UF é obrigatória (2 letras) para desambiguar homônimos — há dezenas de
    "São João" no Brasil. Aceita case-insensitive (``sc`` -> ``SC``) e
    espaços ao redor da vírgula.
    """
    if not raw or not raw.strip():
        raise CityParseError("lista de cidades vazia")

    targets: list[CityTarget] = []
    for chunk in raw.split(";"):
        item = chunk.strip()
        if not item:
            continue
        parts = [p.strip() for p in item.split(",")]
        if len(parts) != 2:
            raise CityParseError(
                f"cidade malformada (use 'Cidade,UF'): '{item}'"
            )
        name, state = parts
        if not name:
            raise CityParseError(f"nome de cidade vazio em: '{item}'")
        state = state.upper()
        if len(state) != 2 or not state.isalpha():
            raise CityParseError(
                f"UF inválida (2 letras): '{parts[1]}' em '{item}'"
            )
        targets.append(CityTarget(name=name, state=state))

    if not targets:
        raise CityParseError("nenhuma cidade informada")

    return targets
