from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urlparse


_TRACKING_HOST_SUFFIXES = (
    "doubleclick.net",
    "google-analytics.com",
)
_NON_PROPERTY_FILENAME_MARKERS = {
    "favicon",
    "loading",
    "logo",
    "noimage",
    "placeholder",
    "qrcode",
    "spacer",
    "spinner",
    "sprite",
    "transparent",
}


def is_suspicious_image_url(value: str) -> bool:
    """Identifica URLs conhecidas por não representarem fotos de imóveis."""
    text = value.strip()
    has_control_character = any(
        ord(character) < 32 or ord(character) == 127
        for character in text
    )
    if not text or has_control_character:
        return True

    parsed = urlparse(text)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    path = unquote(parsed.path).lower()

    if _host_matches(hostname, "facebook.com") and path.rstrip("/") == "/tr":
        return True
    if any(_host_matches(hostname, suffix) for suffix in _TRACKING_HOST_SUFFIXES):
        return True

    filename = PurePosixPath(path).stem
    filename_tokens = list(filter(None, re.split(r"[^a-z0-9]+", filename)))
    collapsed_filename = "".join(filename_tokens)
    return bool(set(filename_tokens) & _NON_PROPERTY_FILENAME_MARKERS) or any(
        marker in collapsed_filename
        for marker in ("noimage", "semfoto")
    )


def build_image_quality_metrics(
    raw_records: Iterable[Mapping[str, Any]],
    normalized_records: Iterable[Mapping[str, Any]],
) -> dict[str, int | float]:
    """Resume cobertura, rejeições e repetição das imagens de um crawl."""
    raw_records = list(raw_records)
    normalized_records = list(normalized_records)
    raw_images = [record.get("imagem") for record in raw_records]
    valid_images = [
        str(record["imagem"]).strip()
        for record in normalized_records
        if _is_supplied(record.get("imagem"))
    ]
    counts = Counter(valid_images)
    dominant_count = max(counts.values(), default=0)
    valid_count = len(valid_images)

    return {
        "total_records": len(raw_records),
        "supplied_image_count": sum(_is_supplied(value) for value in raw_images),
        "valid_image_count": valid_count,
        "invalid_or_missing_count": len(raw_records) - valid_count,
        "suspicious_image_count": sum(
            isinstance(value, str) and is_suspicious_image_url(value)
            for value in raw_images
        ),
        "unique_image_count": len(counts),
        "duplicate_image_count": valid_count - len(counts),
        "dominant_image_count": dominant_count,
        "dominant_image_ratio": round(dominant_count / valid_count, 4)
        if valid_count
        else 0.0,
    }


def _host_matches(hostname: str, suffix: str) -> bool:
    return hostname == suffix or hostname.endswith(f".{suffix}")


def _is_supplied(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True
