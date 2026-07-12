from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin, urlparse

from crawler_machine.normalization.result import NormalizationResult


class UrlNormalizer:
    """Normaliza e valida URLs absolutas e relativas."""

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        source_url = record.get("url") if record else None
        if source_url and not bool(urlparse(text).netloc):
            text = urljoin(str(source_url), text)

        parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return NormalizationResult(
                value=None,
                is_valid=False,
                warnings=[f"URL inválida: {text}"],
                omitted=True,
            )

        return NormalizationResult(value=text, is_valid=True)
