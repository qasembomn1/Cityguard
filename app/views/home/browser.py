from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QWidget

from app.ui.file_browser_dialog import RestrictedBrowserWidget


class BrowserPage(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.browser = RestrictedBrowserWidget(mode="browse", parent=self)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(12)

        hero = QFrame(self)
        hero.setObjectName("browserHero")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(18, 16, 18, 16)
        hero_layout.setSpacing(4)

        title = QLabel("Browser")
        title.setObjectName("browserHeroTitle")
        hero_layout.addWidget(title)

        subtitle = QLabel(
            "Browse recorded files only inside the save path configured in Settings and mounted media storage."
        )
        subtitle.setObjectName("browserHeroSubtitle")
        subtitle.setWordWrap(True)
        hero_layout.addWidget(subtitle)

        root.addWidget(hero)
        root.addWidget(self.browser, 1)

        self.setStyleSheet(
            """
            QWidget {
                background: #0d131c;
                color: #e5edf8;
            }
            QFrame#browserHero {
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 #122135,
                    stop: 0.55 #16263d,
                    stop: 1 #1b2f49
                );
                border: 1px solid #294261;
                border-radius: 18px;
            }
            QLabel#browserHeroTitle {
                color: #f8fbff;
                font-size: 24px;
                font-weight: 800;
            }
            QLabel#browserHeroSubtitle {
                color: #b8c9dd;
                font-size: 13px;
                line-height: 1.45em;
            }
            """
        )

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        self.browser.reload_allowed_roots()
