from PySide6.QtWidgets import QPushButton, QSizePolicy
from PySide6.QtCore import Qt, QVariantAnimation, QEasingCurve, QSize, QTimer
from PySide6.QtGui import QColor


class PrimeButton(QPushButton):
    STYLES = {
        "primary": {
            "bg": "#3B82F6",
            "hover": "#2563EB",
            "press": "#1D4ED8",
            "text": "#FFFFFF",
            "border": "#3B82F6",
        },
        "secondary": {
            "bg": "#64748B",
            "hover": "#475569",
            "press": "#334155",
            "text": "#FFFFFF",
            "border": "#64748B",
        },
        "success": {
            "bg": "#22C55E",
            "hover": "#16A34A",
            "press": "#15803D",
            "text": "#FFFFFF",
            "border": "#22C55E",
        },
        "info": {
            "bg": "#06B6D4",
            "hover": "#0891B2",
            "press": "#0E7490",
            "text": "#FFFFFF",
            "border": "#06B6D4",
        },
        "warning": {
            "bg": "#F59E0B",
            "hover": "#D97706",
            "press": "#B45309",
            "text": "#FFFFFF",
            "border": "#F59E0B",
        },
        "danger": {
            "bg": "#EF4444",
            "hover": "#DC2626",
            "press": "#B91C1C",
            "text": "#FFFFFF",
            "border": "#EF4444",
        },
        "contrast": {
            "bg": "#111827",
            "hover": "#1F2937",
            "press": "#000000",
            "text": "#FFFFFF",
            "border": "#111827",
        },
        "help": {
            "bg": "#A855F7",
            "hover": "#9333EA",
            "press": "#7E22CE",
            "text": "#FFFFFF",
            "border": "#A855F7",
        },
        "light": {
            "bg": "#F8FAFC",
            "hover": "#E2E8F0",
            "press": "#CBD5E1",
            "text": "#0F172A",
            "border": "#CBD5E1",
        },
    }

    def __init__(
        self,
        text="Button",
        variant="primary",
        mode="filled",   # filled, outline, text, ghost
        size="md",       # sm, md, lg
        width=200,
        height=50,
        pill=False,
        parent=None,
    ):
        super().__init__(text, parent)

        self.variant = variant if variant in self.STYLES else "primary"
        self.mode = mode
        self.size_name = size
        self.pill = pill
        self.width = width
        self.height = height

        self._cfg = self.STYLES[self.variant]

        self._bg = QColor(self._cfg["bg"])
        self._hover = QColor(self._cfg["hover"])
        self._press = QColor(self._cfg["press"])
        self._text = QColor(self._cfg["text"])
        self._border = QColor(self._cfg["border"])

        self._current_bg = QColor()
        self._current_text = QColor()
        self._current_border = QColor()

        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setMinimumWidth(110)

        self._apply_size()

        self._hover_anim = QVariantAnimation(self)
        self._hover_anim.setDuration(140)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._hover_anim.valueChanged.connect(self._on_bg_animate)

        self._text_anim = QVariantAnimation(self)
        self._text_anim.setDuration(140)
        self._text_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._text_anim.valueChanged.connect(self._on_text_animate)

        self._border_anim = QVariantAnimation(self)
        self._border_anim.setDuration(140)
        self._border_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._border_anim.valueChanged.connect(self._on_border_animate)

        self._loading = False
        self._original_text = ""
        self._loading_frame = 0
        self._loading_timer = QTimer(self)
        self._loading_timer.timeout.connect(self._on_loading_tick)

        self._set_idle_colors()
        self._update_style()

    def _apply_size(self):
        sizes = {
            "sm": {"h": 32, "fs": 12, "px": 12, "radius": 8},
            "md": {"h": 38, "fs": 13, "px": 16, "radius": 10},
            "lg": {"h": 46, "fs": 14, "px": 20, "radius": 12},
        }
        s = sizes.get(self.size_name, sizes["md"])
        self._height = s["h"]
        self._font_size = s["fs"]
        self._padding_x = s["px"]
        self._radius = self._height // 2 if self.pill else s["radius"]
        self.setFixedHeight(self._height)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(hint.width() + self._padding_x * 2, 110), self._height)

    def _set_idle_colors(self):
        if self.mode == "filled":
            self._current_bg = QColor(self._bg)
            self._current_text = QColor(self._text)
            self._current_border = QColor(self._border)
        elif self.mode == "outline":
            self._current_bg = QColor(0, 0, 0, 0)
            self._current_text = QColor(self._bg)
            self._current_border = QColor(self._border)
        elif self.mode == "text":
            self._current_bg = QColor(0, 0, 0, 0)
            self._current_text = QColor(self._bg)
            self._current_border = QColor(0, 0, 0, 0)
        elif self.mode == "ghost":
            self._current_bg = QColor(self._bg)
            self._current_bg.setAlpha(28)
            self._current_text = QColor(self._bg)
            self._current_border = QColor(0, 0, 0, 0)
        else:
            self._current_bg = QColor(self._bg)
            self._current_text = QColor(self._text)
            self._current_border = QColor(self._border)

    def _hover_targets(self):
        if self.mode == "filled":
            return self._hover, self._text, self._hover
        elif self.mode == "outline":
            bg = QColor(self._bg)
            bg.setAlpha(25)
            return bg, self._hover, self._hover
        elif self.mode == "text":
            bg = QColor(self._bg)
            bg.setAlpha(18)
            return bg, self._hover, QColor(0, 0, 0, 0)
        elif self.mode == "ghost":
            bg = QColor(self._bg)
            bg.setAlpha(46)
            return bg, self._hover, QColor(0, 0, 0, 0)
        return self._hover, self._text, self._hover

    def _press_targets(self):
        if self.mode == "filled":
            return self._press, self._text, self._press
        elif self.mode == "outline":
            bg = QColor(self._bg)
            bg.setAlpha(36)
            return bg, self._press, self._press
        elif self.mode == "text":
            bg = QColor(self._bg)
            bg.setAlpha(24)
            return bg, self._press, QColor(0, 0, 0, 0)
        elif self.mode == "ghost":
            bg = QColor(self._bg)
            bg.setAlpha(60)
            return bg, self._press, QColor(0, 0, 0, 0)
        return self._press, self._text, self._press

    def _animate_to(self, bg, text, border):
        self._hover_anim.stop()
        self._hover_anim.setStartValue(self._current_bg)
        self._hover_anim.setEndValue(bg)
        self._hover_anim.start()

        self._text_anim.stop()
        self._text_anim.setStartValue(self._current_text)
        self._text_anim.setEndValue(text)
        self._text_anim.start()

        self._border_anim.stop()
        self._border_anim.setStartValue(self._current_border)
        self._border_anim.setEndValue(border)
        self._border_anim.start()

    def _on_bg_animate(self, color):
        self._current_bg = QColor(color)
        self._update_style()

    def _on_text_animate(self, color):
        self._current_text = QColor(color)
        self._update_style()

    def _on_border_animate(self, color):
        self._current_border = QColor(color)
        self._update_style()

    def _update_style(self):
        border_width = 1 if self._current_border.alpha() > 0 else 0
        border_rgba = f"rgba({self._current_border.red()}, {self._current_border.green()}, {self._current_border.blue()}, {self._current_border.alpha()})"
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: rgba({self._current_bg.red()}, {self._current_bg.green()}, {self._current_bg.blue()}, {self._current_bg.alpha()});
                color: rgba({self._current_text.red()}, {self._current_text.green()}, {self._current_text.blue()}, {self._current_text.alpha()});
                border: {border_width}px solid {border_rgba};
                border-radius: {self._radius}px;
                padding-left: {self._padding_x}px;
                padding-right: {self._padding_x}px;
                font-size: {self._font_size}px;
                width:{self.width};
                height:{self.height or '100%'};
                font-weight: 600;
            }}
            QPushButton:disabled {{
                background-color: rgba(148, 163, 184, 35);
                color: rgba(148, 163, 184, 140);
                border: 1px solid rgba(148, 163, 184, 60);
            }}
        """)

    def set_loading(self, loading: bool) -> None:
        if self._loading == loading:
            return
        self._loading = loading
        if loading:
            self._original_text = self.text()
            self._loading_frame = 0
            self._on_loading_tick()
            self._loading_timer.start(400)
            self.setEnabled(False)
        else:
            self._loading_timer.stop()
            self.setText(self._original_text)
            self.setEnabled(True)

    def _on_loading_tick(self) -> None:
        dots = ["·", "··", "···"]
        self._loading_frame = (self._loading_frame + 1) % 3
        self.setText(f"{self._original_text} {dots[self._loading_frame]}")

    def enterEvent(self, event):
        if self.isEnabled():
            bg, text, border = self._hover_targets()
            self._animate_to(bg, text, border)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self.isEnabled():
            self._set_idle_colors()
            self._animate_to(self._current_bg, self._current_text, self._current_border)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if self.isEnabled() and event.button() == Qt.LeftButton:
            bg, text, border = self._press_targets()
            self._animate_to(bg, text, border)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self.isEnabled():
            if self.rect().contains(event.position().toPoint()):
                bg, text, border = self._hover_targets()
            else:
                self._set_idle_colors()
                bg, text, border = self._current_bg, self._current_text, self._current_border
            self._animate_to(bg, text, border)
        super().mouseReleaseEvent(event)