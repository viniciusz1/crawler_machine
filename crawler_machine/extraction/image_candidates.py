from __future__ import annotations

import re
from collections.abc import Iterable
from html.parser import HTMLParser

from crawler_machine.image_policy import is_suspicious_image_url


_NON_PROPERTY_ELEMENT_TERMS = (
    "avatar",
    "broker",
    "corretor",
    "facebook",
    "icon",
    "icone",
    "ícone",
    "logo",
    "qrcode",
    "qr code",
    "telegram",
    "whatsapp",
)
_GALLERY_CLASS_MARKERS = (
    "fotorama__img",
    "gallery-image",
    "gallery__image",
    "property-image",
    "property__image",
)


def extract_property_image(
    html: str,
    collected_images: Iterable[str] = (),
) -> str | None:
    """Escolhe a imagem principal antes de recorrer a uma ``img`` genérica."""
    parser = _PropertyImageParser()
    try:
        parser.feed(html)
        parser.close()
    except (AssertionError, ValueError):
        # HTML de terceiros pode ser malformado. Candidatos coletados antes do
        # erro e as mídias do navegador ainda são aproveitáveis.
        pass

    candidate_groups = (
        parser.open_graph,
        parser.twitter,
        parser.data_images,
        parser.gallery_images,
        list(collected_images),
        parser.generic_images,
    )
    for candidates in candidate_groups:
        for candidate in candidates:
            normalized = _normalize_candidate(candidate)
            if normalized is not None:
                return normalized
    return None


def filter_image_candidates(candidates: Iterable[str]) -> list[str]:
    """Remove pixels, placeholders e duplicatas preservando a ordem."""
    filtered: list[str] = []
    for candidate in candidates:
        normalized = _normalize_candidate(candidate)
        if normalized is not None and normalized not in filtered:
            filtered.append(normalized)
    return filtered


class _PropertyImageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.open_graph: list[str] = []
        self.twitter: list[str] = []
        self.data_images: list[str] = []
        self.gallery_images: list[str] = []
        self.generic_images: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = {name.lower(): value or "" for name, value in attrs}
        lowered_tag = tag.lower()

        if lowered_tag == "meta":
            self._collect_metadata(attributes)
            return

        data_image = attributes.get("data-img")
        lazy_image = (
            attributes.get("data-src")
            or attributes.get("data-lazy-src")
            or attributes.get("data-original")
        )
        srcset_image = _largest_srcset_candidate(
            attributes.get("data-srcset") or attributes.get("srcset", "")
        )

        if lowered_tag != "img":
            for candidate in (data_image, lazy_image):
                if candidate:
                    self.data_images.append(candidate)
            if lowered_tag == "source" and srcset_image:
                self.data_images.append(srcset_image)
            return

        if _is_non_property_element(attributes):
            return

        if data_image:
            self.data_images.append(data_image)

        image = data_image or lazy_image or srcset_image or attributes.get("src")
        if not image:
            return

        class_name = attributes.get("class", "").lower()
        if any(marker in class_name for marker in _GALLERY_CLASS_MARKERS):
            self.gallery_images.append(image)
        elif lazy_image:
            self.data_images.append(image)
        else:
            self.generic_images.append(image)

    def _collect_metadata(self, attributes: dict[str, str]) -> None:
        key = (attributes.get("property") or attributes.get("name") or "").lower()
        content = attributes.get("content")
        if not content:
            return
        if key in {"og:image", "og:image:secure_url"}:
            self.open_graph.append(content)
        elif key in {"twitter:image", "twitter:image:src"}:
            self.twitter.append(content)


def _is_non_property_element(attributes: dict[str, str]) -> bool:
    for dimension in (attributes.get("width"), attributes.get("height")):
        if dimension and _numeric_dimension(dimension) <= 2:
            return True

    description = " ".join(
        attributes.get(name, "")
        for name in ("alt", "aria-label", "class", "id", "title")
    ).lower()
    return any(term in description for term in _NON_PROPERTY_ELEMENT_TERMS)


def _numeric_dimension(value: str) -> float:
    match = re.match(r"\s*(\d+(?:\.\d+)?)", value)
    return float(match.group(1)) if match else float("inf")


def _largest_srcset_candidate(srcset: str) -> str | None:
    candidates = [
        item.strip().split()[0]
        for item in srcset.split(",")
        if item.strip()
    ]
    return candidates[-1] if candidates else None


def _normalize_candidate(candidate: object) -> str | None:
    if not isinstance(candidate, str):
        return None
    normalized = candidate.strip()
    if not normalized or is_suspicious_image_url(normalized):
        return None
    return normalized
