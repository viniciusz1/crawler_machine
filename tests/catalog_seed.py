"""Helpers para popular catálogos mínimos nos testes do crawler.

O seeding oficial dos catálogos vive fora deste repositório (tipicamente em
um serviço backend ou sob gestão de DBA). Este módulo mantém apenas os dados
mínimos necessários para os testes Python que precisam consultar as tabelas
do schema crawler.
"""

from __future__ import annotations

import json
from typing import Any


def seed_test_catalogs(connection: Any) -> None:
    """Insere os catálogos mínimos usados pelos testes do crawler."""
    with connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO crawler.cities (name, slug, state)
                VALUES (%s, %s, %s)
                ON CONFLICT (slug, state) DO NOTHING
                RETURNING id
                """,
                ("Jaraguá do Sul", "jaragua-do-sul", "SC"),
            )
            row = cursor.fetchone()
            if row is not None:
                city_id = row[0]
            else:
                cursor.execute(
                    "SELECT id FROM crawler.cities WHERE slug = %s AND state = %s",
                    ("jaragua-do-sul", "SC"),
                )
                city_id = cursor.fetchone()[0]

            neighborhoods = [
                (city_id, "Centro", "centro", json.dumps([])),
                (city_id, "Vila Lenzi", "vila-lenzi", json.dumps(["vila lenzi"])),
            ]
            cursor.executemany(
                """
                INSERT INTO crawler.neighborhoods (city_id, name, slug, aliases)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (city_id, slug) DO NOTHING
                """,
                neighborhoods,
            )

            property_types = [
                ("Apartamento", "apartamento", json.dumps(["apto", "apart"])),
                ("Casa", "casa", json.dumps(["casa residencial"])),
                ("Sobrado", "sobrado", json.dumps([])),
                ("Sobrado Geminado", "sobrado-geminado", json.dumps(["sobrado geminado", "casa geminada"])),
                ("Geminado", "geminado", json.dumps(["casa geminado"])),
                ("Terreno", "terreno", json.dumps(["terreno urbano", "terreno rural"])),
                ("Sala Comercial", "sala-comercial", json.dumps(["sala comercial", "sala"])),
            ]
            cursor.executemany(
                """
                INSERT INTO crawler.property_types (name, slug, aliases)
                VALUES (%s, %s, %s)
                ON CONFLICT (slug) DO NOTHING
                """,
                property_types,
            )
