from __future__ import annotations

import html as html_lib
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlparse

from crawler_machine.discovery.items_catalog.constants import (
    LISTING_ENTRYPOINT_PATH_RE,
    PAGINATION_CONTAINER_RE,
    PROPERTY_CARD_LINK_CLASS_RE,
)
from crawler_machine.discovery.items_catalog.models import PageControl, PageSnapshot


class _DOMInspectorParser(HTMLParser):
    """Extrai links e controles interativos de um documento HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.card_links: list[str] = []
        self.controls: list[PageControl] = []
        self._stack: list[tuple[str, dict[str, str]]] = []
        self._current_control: dict[str, Any] | None = None
        self._control_counter = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag_lower = tag.lower()
        attr_map = {k.lower(): (v or "") for k, v in attrs}
        self._stack.append((tag_lower, attr_map))

        if tag_lower in {"a", "link"} and attr_map.get("href"):
            href = attr_map["href"].strip()
            if tag_lower == "a":
                in_chrome = self._in_chrome_context()
                cls_str = attr_map.get("class", "")
                if PROPERTY_CARD_LINK_CLASS_RE.search(cls_str):
                    self.card_links.append(href)
                    self.links.append(href)
                elif not in_chrome:
                    self.links.append(href)
                elif LISTING_ENTRYPOINT_PATH_RE.match(urlparse(href).path or ""):
                    self.links.append(href)
            elif "next" in attr_map.get("rel", "").lower():
                self.controls.append(
                    PageControl(
                        control_id=f"link-{self._control_counter}",
                        tag="link",
                        text="",
                        href=href,
                        rel=attr_map.get("rel", ""),
                        in_pagination=True,
                    )
                )
                self._control_counter += 1

        has_pw_id = bool(attr_map.get("data-cm-control-id"))
        cls_and_id = f"{attr_map.get('class', '')} {attr_map.get('id', '')}"
        is_pagination_div = (
            tag_lower in {"div", "span", "li"}
            and bool(re.search(r"(?:btn-paginacao|PageNumber|page-numbers)", cls_and_id, re.IGNORECASE))
        )
        is_interactive = (
            has_pw_id
            or tag_lower in {"a", "button"}
            or attr_map.get("role", "").lower() == "button"
            or (
                tag_lower == "input"
                and attr_map.get("type", "").lower() in {"button", "submit"}
            )
            or is_pagination_div
            or (
                tag_lower == "span"
                and self._is_active_attrs(attr_map)
                and self._in_pagination_context()
            )
        )
        if is_interactive and self._current_control is None:
            control_id = attr_map.get("data-cm-control-id") or f"ctrl-{self._control_counter}"
            self._control_counter += 1
            if tag_lower == "input":
                self.controls.append(
                    PageControl(
                        control_id=control_id,
                        tag=tag_lower,
                        text=attr_map.get("value", "").strip(),
                        href=None,
                        rel=attr_map.get("rel", ""),
                        aria_label=attr_map.get("aria-label", ""),
                        title=attr_map.get("title", ""),
                        classes=self._combined_classes(attr_map),
                        in_pagination=self._in_pagination_context(),
                        is_active=self._is_active_in_stack(),
                        disabled=self._is_disabled_in_stack(),
                        in_chrome=self._in_chrome_context(),
                    )
                )
                self._stack.pop()
                return
            self._current_control = {
                "control_id": control_id,
                "tag": tag_lower,
                "stack_depth": len(self._stack),
                "text_parts": [],
                "href": attr_map.get("href") or None,
                "rel": attr_map.get("rel", ""),
                "aria_label": attr_map.get("aria-label", ""),
                "title": attr_map.get("title", ""),
                "classes": self._combined_classes(attr_map),
                "in_pagination": self._in_pagination_context(),
                "is_active": self._is_active_in_stack(),
                "disabled": self._is_disabled_in_stack(),
                "in_chrome": self._in_chrome_context(),
            }

    def handle_data(self, data: str) -> None:
        if self._current_control is not None:
            self._current_control["text_parts"].append(data)

    def handle_endtag(self, tag: str) -> None:
        tag_lower = tag.lower()
        popped_depth: int | None = None
        for idx in range(len(self._stack) - 1, -1, -1):
            if self._stack[idx][0] == tag_lower:
                popped_depth = idx + 1
                self._stack.pop(idx)
                break

        if (
            self._current_control is not None
            and self._current_control["tag"] == tag_lower
            and (
                popped_depth == self._current_control["stack_depth"]
                or len(self._stack) < self._current_control["stack_depth"]
            )
        ):
            raw_text = " ".join(self._current_control["text_parts"])
            clean_text = re.sub(r"\s+", " ", html_lib.unescape(raw_text)).strip()
            self.controls.append(
                PageControl(
                    control_id=self._current_control["control_id"],
                    tag=self._current_control["tag"],
                    text=clean_text,
                    href=self._current_control["href"],
                    rel=self._current_control["rel"],
                    aria_label=self._current_control["aria_label"],
                    title=self._current_control["title"],
                    classes=self._current_control["classes"],
                    in_pagination=self._current_control["in_pagination"],
                    is_active=self._current_control["is_active"],
                    disabled=self._current_control["disabled"],
                    in_chrome=self._current_control["in_chrome"],
                )
            )
            self._current_control = None

    def _in_pagination_context(self) -> bool:
        for tag, attrs in self._stack:
            combined = (
                f"{attrs.get('class', '')} {attrs.get('id', '')} "
                f"{attrs.get('aria-label', '')} {attrs.get('role', '')}"
            )
            if PAGINATION_CONTAINER_RE.search(combined):
                return True
            if tag == "nav" and not re.search(r"(?:menu|header|top|navbar)", combined, re.IGNORECASE):
                return True
        return False

    def _in_chrome_context(self) -> bool:
        for tag, attrs in self._stack:
            if tag in {"header", "footer", "nav"}:
                return True
            combined = f"{attrs.get('class', '')} {attrs.get('id', '')}"
            if re.search(
                r"(?:^|\s|_|-)footer(?:\s|_|-|$)|box_link_mais_filtros",
                combined,
                re.IGNORECASE,
            ):
                return True
        return False

    def _combined_classes(self, current_attrs: dict[str, str]) -> str:
        classes = [current_attrs.get("class", ""), current_attrs.get("id", "")]
        if len(self._stack) >= 2:
            parent_tag, parent_attrs = self._stack[-2]
            if parent_tag in {"li", "span", "div"}:
                classes.append(parent_attrs.get("class", ""))
                classes.append(parent_attrs.get("id", ""))
        return " ".join(c for c in classes if c).strip()

    def _is_active_in_stack(self) -> bool:
        for tag, attrs in self._stack[-2:]:
            if tag in {"a", "button", "li", "span", "div"} and self._is_active_attrs(attrs):
                return True
        return False

    @staticmethod
    def _is_active_attrs(attrs: dict[str, str]) -> bool:
        if attrs.get("aria-current", "").lower() in {"page", "true"}:
            return True
        classes = f" {attrs.get('class', '').lower()} "
        return any(
            token in classes
            for token in (
                " active ",
                " current ",
                " selected ",
                " is-active ",
                "--active ",
                "--current ",
            )
        )

    def _is_disabled_in_stack(self) -> bool:
        for tag, attrs in self._stack[-2:]:
            if tag in {"a", "button", "li", "span", "input", "div"}:
                if "disabled" in attrs or attrs.get("aria-disabled", "").lower() == "true":
                    return True
                classes = f" {attrs.get('class', '').lower()} "
                if (
                    " disabled " in classes
                    or " is-disabled " in classes
                    or "--disabled" in classes
                ):
                    return True
        return False


def parse_page_snapshot(url: str, html: str) -> PageSnapshot:
    """Constrói um ``PageSnapshot`` a partir de URL e HTML renderizado."""
    parser = _DOMInspectorParser()
    parser.feed(html)
    json_links = re.findall(r'["\']link["\']\s*:\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
    all_links = [*parser.links, *json_links]
    return PageSnapshot(
        url=url,
        html=html,
        links=all_links,
        controls=parser.controls,
        card_links=parser.card_links,
    )
