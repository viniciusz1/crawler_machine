from __future__ import annotations

from crawler_machine.discovery.items_catalog.browser import (
    FakeListingBrowser,
    PlaywrightListingBrowser,
)
from crawler_machine.discovery.items_catalog.constants import DEFAULT_PROPERTY_PATTERNS
from crawler_machine.discovery.items_catalog.discoverer import (
    PlaywrightListingDiscoverer,
)
from crawler_machine.discovery.items_catalog.dom_parser import parse_page_snapshot
from crawler_machine.discovery.items_catalog.models import (
    ListingBrowser,
    ListingBrowserSession,
    PageControl,
    PageSnapshot,
    PaginationAction,
)
from crawler_machine.discovery.items_catalog.paginator import CatalogPaginator
from crawler_machine.discovery.items_catalog.url_classifier import URLClassifier

__all__ = [
    "CatalogPaginator",
    "DEFAULT_PROPERTY_PATTERNS",
    "FakeListingBrowser",
    "ListingBrowser",
    "ListingBrowserSession",
    "PageControl",
    "PageSnapshot",
    "PaginationAction",
    "PlaywrightListingBrowser",
    "PlaywrightListingDiscoverer",
    "URLClassifier",
    "parse_page_snapshot",
]
