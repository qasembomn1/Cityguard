import sys
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QTextEdit,
)


class AppDialog(QDialog):
    def __init__(
        self,
        title: str = "Dialog",
        content: Optional[QWidget] = None,
        parent: Optional[QWidget] = None,
        modal: bool = True,
        width: int = 700,
        height: int = 300,
        show_footer: bool = True,
        ok_text: str = "OK",
        cancel_text: str = "Cancel",
    ):
        super().__init__(parent)

        self.setWindowTitle(title)
        self.setModal(modal)
        self.resize(width, height)

        self.setStyleSheet("""
            QDialog {
                background: white;
                border-radius: 12px;
            }
            QLabel#dialogTitle {
                font-size: 18px;
                font-weight: 600;
            }
            QPushButton {
                padding: 8px 14px;
                border-radius: 8px;
                min-width: 90px;
            }
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # Header
        header_layout = QHBoxLayout()
        self.title_label = QLabel(title)
        self.title_label.setObjectName("dialogTitle")

        self.close_button = QPushButton("✕")
        self.close_button.setFixedWidth(36)
        self.close_button.clicked.connect(self.reject)

        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.close_button)

        root.addLayout(header_layout)

        # Content
        self.content_container = QWidget()
        self.content_layout = QVBoxLayout(self.content_container)
        self.content_layout.setContentsMargins(0, 0, 0, 0)

        if content:
            self.set_content(content)

        root.addWidget(self.content_container, 1)

        # Footer
        self.footer_widget = QWidget()
        footer_layout = QHBoxLayout(self.footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        footer_layout.addStretch()

        self.cancel_button = QPushButton(cancel_text)
        self.ok_button = QPushButton(ok_text)

        self.cancel_button.clicked.connect(self.reject)
        self.ok_button.clicked.connect(self.accept)

        footer_layout.addWidget(self.cancel_button)
        footer_layout.addWidget(self.ok_button)

        if show_footer:
            root.addWidget(self.footer_widget)
        else:
            self.footer_widget.hide()

    def set_content(self, widget: QWidget):
        self.clear_content()
        self.content_layout.addWidget(widget)

    def clear_content(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            child = item.widget()
            if child:
                child.setParent(None)

    def set_footer_visible(self, visible: bool):
        self.footer_widget.setVisible(visible)

    def set_ok_text(self, text: str):
        self.ok_button.setText(text)

    def set_cancel_text(self, text: str):
        self.cancel_button.setText(text)

    def set_title(self, title: str):
        self.setWindowTitle(title)
        self.title_label.setText(title)


# Demo content widget
class TextContent(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Write something:"))

        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Type here...")
        layout.addWidget(self.editor)


# Demo main window
class DemoWindow(QWidget):


    def _init_(self):
        super()._init_()
        self.setWindowTitle("AppDialog - PySide6")  
        content = TextContent()

        dialog = AppDialog(
            title="Edit Text",
            content=content,
            parent=self,
            width=700,
            height=300,
            ok_text="Save",
            cancel_text="Close",
        )

        if dialog.exec():
            print("Saved text:", content.editor.toPlainText())

        dialog.exec()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = DemoWindow()
    window.show()

    sys.exit(app.exec())