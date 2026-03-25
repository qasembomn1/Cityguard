from __future__ import annotations

from app.views.section_sidebar import SECTION_SIDEBAR_STYLES, SectionSidebar


REPORT_NAV_ITEMS = [
    {
        "label": "LPR",
        "icon": "report.svg",
        "path": "/report/lpr",
        "tooltip": "LPR Report",
        "menu_label": "LPR Report",
        "group": "LPR",
    },
    {
        "label": "Face",
        "icon": "faces.svg",
        "path": "/report/face",
        "tooltip": "Face Report",
        "menu_label": "Face Report",
        "group": "Face",
    },
    {
        "label": "Count",
        "icon": "view.svg",
        "path": "/report/face_count",
        "tooltip": "Face Count Report",
        "menu_label": "Face Count Report",
        "group": "Face",
    },
]

REPORT_MENU_SECTIONS = [
    {
        "label": "LPR",
        "items": [
            {"label": "LPR Report", "path": "/report/lpr"},
        ],
    },
    {
        "label": "Face",
        "items": [
            {"label": "Face Report", "path": "/report/face"},
            {"label": "Face Count Report", "path": "/report/face_count"},
        ],
    },
]

REPORT_SIDEBAR_STYLES = SECTION_SIDEBAR_STYLES


class ReportSidebar(SectionSidebar):
    def __init__(self, current_path: str, parent=None) -> None:
        super().__init__(current_path, REPORT_NAV_ITEMS, parent)
