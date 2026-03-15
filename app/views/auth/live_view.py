import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.utils.qt_digits import install_english_digit_support
from app.views.home.stream.live_view import CameraDashboard


class StartupLiveViewPage(CameraDashboard):
    def __init__(self, parent=None):
        super().__init__(startup_mode=True)
        self.setParent(parent)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.setWindowTitle("City Guard Startup Live View")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = StartupLiveViewPage()
    install_english_digit_support(window)
    window.showFullScreen()
    window.show()
    sys.exit(app.exec())
