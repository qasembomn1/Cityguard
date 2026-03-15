from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget

from app.views.face.report import BaseFaceReportPage


class FaceCountReportPage(BaseFaceReportPage):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(
            endpoint="/api/v1/face_report/count_report",
            title="Face Count Report",
            hint=(
                "Run the face count report from a top filter panel like the LPR pages. "
                "This posts `date_from`, `date_to`, and `camera_ids` to `/api/v1/face_report/count_report`."
            ),
            export_prefix="face-count-report",
            toast_title="Face Count Report",
            parent=parent,
        )
