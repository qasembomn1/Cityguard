import os
import sys
from typing import Optional

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QLabel, QDialog, QLineEdit, QVBoxLayout, QWidget

if __package__ in (None, ""):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

from app.ui.dialog import PrimeDialog
from app.ui.input import PrimeInput


class PrimePasswordDialog(PrimeDialog):
    def __init__(
        self,
        title: str = "Enter Password",
        message: str = "Enter your password to continue.",
        parent: Optional[QWidget] = None,
        ok_text: str = "Confirm",
        cancel_text: str = "Cancel",
        width: int = 460,
        height: int = 250,
        closable: bool = True,
        dismissable_mask: bool = True,
        draggable: bool = False,
    ) -> None:
        self._content_widget = QWidget()
        self._content_layout = QVBoxLayout(self._content_widget)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        self._content_layout.setSpacing(12)

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

        self.password_input = PrimeInput(placeholder_text="Enter password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.textChanged.connect(self._clear_error)
        self.password_input.returnPressed.connect(self.accept)
        self._content_layout.addWidget(self.password_input)

        self.error_label = QLabel("")
        self.error_label.hide()
        self.error_label.setStyleSheet("color: #f87171; font-size: 12px;")
        self._content_layout.addWidget(self.error_label)

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

    def showEvent(self, event) -> None:
        super().showEvent(event)
        QTimer.singleShot(0, self.password_input.setFocus)

    def set_message(self, message: str) -> None:
        self.message_label.setText(message)

    def password(self) -> str:
        return self.password_input.text().strip()

    def _clear_error(self) -> None:
        self.error_label.hide()
        self.error_label.setText("")
        self.password_input.clear_error()

    def accept(self) -> None:
        if self.password():
            self._clear_error()
            super().accept()
            return
        self.error_label.setText("Password is required.")
        self.error_label.show()
        self.password_input.set_error()
        self.password_input.setFocus()

    @classmethod
    def get_password(
        cls,
        parent: Optional[QWidget] = None,
        title: str = "Enter Password",
        message: str = "Enter your password to continue.",
        ok_text: str = "Confirm",
        cancel_text: str = "Cancel",
        width: int = 460,
        height: int = 250,
        closable: bool = True,
        dismissable_mask: bool = True,
        draggable: bool = False,
    ) -> Optional[str]:
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
        if dialog.exec() == QDialog.Accepted:
            return dialog.password()
        return None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    password = PrimePasswordDialog.get_password(
        title="Remove IP",
        message="Enter your password to remove the selected IP address.",
        ok_text="Remove IP",
    )
    print(password if password else "cancelled")
