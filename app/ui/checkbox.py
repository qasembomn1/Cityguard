from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QCheckBox


class PrimeCheckBox(QCheckBox):
    def __init__(self, text="", parent=None, box_size=18):
        super().__init__(text, parent)
        self._box_size = max(14, box_size)
        self._gap = 14
        self._padding_x = 8
        self._padding_y = 10
        self._focus_padding = 3
        self._hovered = False
        self._pressed = False

        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(self._box_size + self._padding_y + (self._focus_padding * 2))

    def sizeHint(self):
        fm = QFontMetrics(self.font())
        text_w = fm.horizontalAdvance(self.text())
        text_h = fm.height()
        height = max(self._box_size, text_h) + self._padding_y + (self._focus_padding * 2)
        width = (
            (self._padding_x * 2)
            + (self._focus_padding * 2)
            + self._box_size
            + self._gap
            + text_w
            + 8
        )
        return QSize(width, height)

    def setText(self, text):
        super().setText(text)
        self.updateGeometry()
        self.update()

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._pressed = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.isEnabled():
            self._pressed = True
            self.update()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        box_y = (rect.height() - self._box_size) // 2
        box_x = self._padding_x + self._focus_padding
        box_rect = QRect(box_x, box_y, self._box_size, self._box_size)

        if not self.isEnabled():
            border = QColor("#4b5563")
            fill = QColor("#1f2937")
            text_color = QColor("#6b7280")
            check = QColor("#9ca3af")
        elif self.isChecked():
            border = QColor("#2563eb") if self._pressed else QColor("#3b82f6")
            fill = QColor("#2563eb") if self._pressed else QColor("#3b82f6")
            text_color = QColor("#f8fafc")
            check = QColor("#ffffff")
        else:
            border = QColor("#93a4b8") if self._hovered else QColor("#64748b")
            fill = QColor("#1f2937")
            text_color = QColor("#e5e7eb")
            check = QColor("#ffffff")

        painter.setPen(QPen(border, 1.4))
        painter.setBrush(fill)
        painter.drawRoundedRect(box_rect, 5, 5)

        if self.isChecked():
            check_pen = QPen(check, 2.1)
            check_pen.setCapStyle(Qt.RoundCap)
            check_pen.setJoinStyle(Qt.RoundJoin)
            painter.setPen(check_pen)
            x = box_rect.x()
            y = box_rect.y()
            s = self._box_size
            painter.drawLine(x + int(s * 0.23), y + int(s * 0.56), x + int(s * 0.44), y + int(s * 0.74))
            painter.drawLine(x + int(s * 0.44), y + int(s * 0.74), x + int(s * 0.78), y + int(s * 0.30))

        if self.hasFocus():
            focus_pen = QPen(QColor(108, 99, 255, 170), 1.4)
            painter.setPen(focus_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(
                box_rect.adjusted(
                    -self._focus_padding,
                    -self._focus_padding,
                    self._focus_padding,
                    self._focus_padding,
                ),
                7,
                7,
            )

        text_left = box_rect.right() + 1 + self._gap
        text_rect = QRect(
            text_left,
            0,
            max(0, rect.width() - text_left - self._padding_x),
            rect.height(),
        )
        text = QFontMetrics(self.font()).elidedText(self.text(), Qt.TextElideMode.ElideRight, text_rect.width())
        painter.setPen(text_color)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, text)
