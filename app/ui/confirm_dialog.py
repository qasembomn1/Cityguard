import os
import sys
from typing import Optional

from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout, QWidget, QDialog

if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.ui.dialog import PrimeDialog


class PrimeConfirmDialog(PrimeDialog):
    def __init__(
        self,
        title: str = "Confirm",
        message: str = "Are you sure?",
        parent: Optional[QWidget] = None,
        ok_text: str = "Confirm",
        cancel_text: str = "Cancel",
        width: int = 460,
        height: int = 220,
        closable: bool = True,
        dismissable_mask: bool = True,
        draggable: bool = False,
    ) -> None:
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(10)

        self.message_label = QLabel(message)
        self.message_label.setWordWrap(True)
        self.message_label.setStyleSheet(
            """
            QLabel {
                color: #dbe4f0;
                font-size: 14px;
                line-height: 1.5;
            }
            """
        )
        self._content_layout.addWidget(self.message_label)

        super().__init__(
            title=title,
            content=self._content_widget,
            parent=parent,
            width=width,
            height=height,
            show_footer=True,
            ok_text=ok_text,
            cancel_text=cancel_text,
            closable=closable,
            dismissable_mask=dismissable_mask,
            draggable=draggable,
        )

        self.ok_button.setDefault(True)
        self.ok_button.setAutoDefault(True)
        self.cancel_button.setAutoDefault(False)

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    @classmethod
    def ask(
        cls,
        parent: Optional[QWidget] = None,
        title: str = "Confirm",
        message: str = "Are you sure?",
        ok_text: str = "Confirm",
        cancel_text: str = "Cancel",
        width: int = 460,
        height: int = 220,
        closable: bool = True,
        dismissable_mask: bool = True,
        draggable: bool = False,
    ) -> bool:
        dialog = cls(
            title=title,
            message=message,
            parent=parent,
            ok_text=ok_text,
            cancel_text=cancel_text,
            width=width,
            height=height,
            closable=closable,
            dismissable_mask=dismissable_mask,
            draggable=draggable,
        )
        return dialog.exec() == QDialog.Accepted


if __name__ == "__main__":
    app = QApplication(sys.argv)
    result = PrimeConfirmDialog(
        title="Delete Record",
        message="Are you sure you want to delete this item? This action cannot be undone.",
        ok_text="Delete",
        cancel_text="Keep",
    ).exec()
    print("accepted" if result == QDialog.Accepted else "rejected")
