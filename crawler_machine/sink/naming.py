from __future__ import annotations

import re

from unidecode import unidecode


def build_source_name(base_url: str, explicit_name: str | None = None) -> str:
    """Gera um slug de fonte a partir da URL base ou nome explícito."""
    name = explicit_name or base_url
    slug = re.sub(r"^https?://", "", name.lower())
    slug = unidecode(slug)
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug
