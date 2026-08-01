from __future__ import annotations

from typing import Any
from urllib.parse import urljoin, urlparse

from crawler_machine.normalization.result import NormalizationResult


class ImageNormalizer:
    """Normaliza e valida URLs de imagem."""

    def normalize(self, value: Any, record: dict[str, Any] | None = None) -> NormalizationResult:
        if value is None:
            return NormalizationResult(value=None, omitted=True)

        text = str(value).strip()
        if not text:
            return NormalizationResult(value=None, omitted=True)

        parsed = urlparse(text)
        if (not parsed.scheme or not parsed.netloc) and record is not None:
            page_url = record.get("url")
            if isinstance(page_url, str):
                text = urljoin(page_url, text)
                parsed = urlparse(text)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return NormalizationResult(
                value=None,
                is_valid=False,
                warnings=[f"URL de imagem inválida: {text}"],
                omitted=True,
            )

        return NormalizationResult(value=text, is_valid=True)
