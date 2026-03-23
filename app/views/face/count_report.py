from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from app.views.face.report import BaseFaceReportPage


class FaceCountReportPage(BaseFaceReportPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            current_path="/report/face_count",
            endpoint="/api/v1/face_report/count_report",
            title="Face Count Report",
            hint=(
                "Run the face count report from the left filter sidebar like the search pages. "
            ),
            export_prefix="face-count-report",
            toast_title="Face Count Report",
            parent=parent,
        )
