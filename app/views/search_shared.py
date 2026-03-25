
from __future__ import annotations

from app.views.section_sidebar import SECTION_SIDEBAR_STYLES, SectionSidebar


SEARCH_NAV_ITEMS = [
    {
        "label": "LPR",
        "icon": "search.svg",
        "path": "/search/lpr",
        "tooltip": "LPR Search",
        "menu_label": "LPR Search",
        "group": "LPR",
    },
    {
        "label": "Face",
        "icon": "faces.svg",
        "path": "/search/face",
        "tooltip": "Face Search",
        "menu_label": "Face Search",
        "group": "Face",
    },
    {
        "label": "Repeat",
        "icon": "record.svg",
        "path": "/search/lpr/repeated",
        "tooltip": "Repeated Search",
        "menu_label": "Repeated Search",
        "group": "LPR",
    },
]

SEARCH_MENU_SECTIONS = [
    {
        "label": "LPR",
        "items": [
            {"label": "LPR Search", "path": "/search/lpr"},
            {"label": "Repeated Search", "path": "/search/lpr/repeated"},
        ],
    },
    {
        "label": "Face",
        "items": [
            {"label": "Face Search", "path": "/search/face"},
        ],
    },
]

SEARCH_SIDEBAR_STYLES = SECTION_SIDEBAR_STYLES


class SearchSidebar(SectionSidebar):
    def __init__(self, current_path: str, parent=None) -> None:
        super().__init__(current_path, SEARCH_NAV_ITEMS, parent)
