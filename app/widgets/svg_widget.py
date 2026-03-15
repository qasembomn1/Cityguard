from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter
from PySide6.QtSvg import QSvgRenderer


class SvgWidget(QWidget):
    def __init__(self, svg_path: str, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(svg_path)

    def setSvg(self, svg_path: str):
        """Change SVG file dynamically"""
        self.renderer.load(svg_path)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        self.renderer.render(painter, self.rect())
        