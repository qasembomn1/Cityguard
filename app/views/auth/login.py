import sys
import os
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve, QTimer, QRect, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QLinearGradient
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFrame,
    QSizePolicy,
    QGraphicsDropShadowEffect,
    QPushButton,
)
from app.widgets.svg_widget import SvgWidget
from app.ui.button import PrimeButton
from app.ui.input import PrimeInput
from app.ui.toast import PrimeToastHost
from app.services.auth.auth_service import AuthService
from app.utils.qt_digits import install_english_digit_support
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
LOGO_PATH = os.path.join(BASE_DIR, "resources","Logo.svg")
CARD_RADIUS = 24

class FloatingCircle(QWidget):
    def __init__(self, color: QColor, size: int, parent=None):
        super().__init__(parent)
        self._color = color
        self.resize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = QColor(self._color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(self.rect())


class GlassCard(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("glassCard")
        self.setStyleSheet(
            """
            QFrame#glassCard {
                background-color: rgba(255, 255, 255, 18);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: %dpx;
            }
        """
            % CARD_RADIUS
        )

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 15)
        shadow.setColor(QColor(0, 0, 0, 160))
        self.setGraphicsEffect(shadow)


class LoginWindow(QWidget):
    login_success = Signal()
    back_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("City Guard Login")
        self.resize(1200, 760)
        self.setMinimumSize(900, 620)

        self.is_loading = False
        self.auth_service = AuthService()
        self.toast = PrimeToastHost(self)

        self.setup_ui()
        self.setup_animations()
        self.login_button.clicked.connect(self.handle_login)
        self.back_button.clicked.connect(self._handle_back)
        self.username_input.returnPressed.connect(self._focus_password)
        self.password_input.returnPressed.connect(self.handle_login)

    def _focus_password(self):
        self.password_input.setFocus()

    def setup_ui(self):
        self.setStyleSheet(
            """
            QWidget {
                font-family: 'Segoe UI', Arial, sans-serif;
                color: white;
                background: transparent;
            }
            
            
            
            QLabel#titleLabel {
                font-size: 32px;
                font-weight: 700;
                color: white;
            }

            QLabel#subtitleLabel {
                font-size: 14px;
                color: rgba(255, 255, 255, 0.65);
            }

            QLabel#fieldLabel {
                font-size: 13px;
                font-weight: 600;
                color: rgba(255, 255, 255, 0.88);
                margin-left: 4px;
            }

            QLabel#errorLabel {
                font-size: 12px;
                color: #ff6b81;
                margin-left: 4px;
            }

            QPushButton#loginButton {
                background-color: #6c63ff;
                border: none;
                border-radius: 14px;
                padding: 14px;
                font-size: 14px;
                font-weight: 700;
                color: white;
            }

            QPushButton#loginButton:hover {
                background-color: #7a72ff;
            }

            QPushButton#loginButton:pressed {
                background-color: #5b53ec;
            }

            QPushButton#backButton {
                background-color: rgba(255, 255, 255, 0.08);
                border: 1px solid rgba(255, 255, 255, 0.18);
                border-radius: 14px;
                padding: 12px;
                font-size: 13px;
                font-weight: 700;
                color: rgba(255, 255, 255, 0.9);
            }

            QPushButton#backButton:hover {
                background-color: rgba(255, 255, 255, 0.12);
                border: 1px solid rgba(255, 255, 255, 0.28);
            }

            QPushButton#backButton:pressed {
                background-color: rgba(255, 255, 255, 0.16);
            }

            QPushButton#toggleButton {
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.7);
                font-size: 12px;
                padding-right: 10px;
            }

            QFrame#dividerLine {
                background-color: rgba(255, 255, 255, 0.13);
                min-height: 1px;
                max-height: 1px;
            }

            QLabel#dividerText {
                background-color: rgba(17, 17, 17, 0.9);
                color: rgba(255, 255, 255, 0.45);
                font-size: 11px;
                padding: 4px 10px;
                border-radius: 10px;
            }

            QLabel#footerLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.45);
            }

            QLabel#versionLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.45);
            }

            QLabel#versionValue {
                font-size: 12px;
                font-weight: 700;
                color: #6c63ff;
            }

            QLabel#shieldLabel {
                font-size: 12px;
                color: rgba(255, 255, 255, 0.5);
            }

            QLabel#logoCircle {
                background-color: rgba(108, 99, 255, 0.16);
                border-radius: 46px;
                color: white;
                font-size: 34px;
                font-weight: 800;
            }
        """
        )

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(32, 32, 32, 32)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.circle_left = FloatingCircle(QColor(255, 255, 255, 18), 700, self)
        self.circle_right = FloatingCircle(QColor(255, 255, 255, 16), 420, self)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = GlassCard()
        self.card.setMaximumWidth(450)
        self.card.setMinimumWidth(500)

        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(36, 34, 36, 28)
        card_layout.setSpacing(18)

        # Logo and header
        logo_wrap = QVBoxLayout()
        logo_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_wrap.setSpacing(10)

        logo = SvgWidget(LOGO_PATH)
        logo.setFixedSize(92, 92)

        title = QLabel("Welcome Back")
        title.setObjectName("titleLabel")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        subtitle = QLabel("Sign in to access your dashboard")
        subtitle.setObjectName("subtitleLabel")
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)

        logo_wrap.addWidget(logo, alignment=Qt.AlignmentFlag.AlignCenter)
        logo_wrap.addWidget(title)
        logo_wrap.addWidget(subtitle)

        card_layout.addLayout(logo_wrap)

        # Username
        user_label = QLabel("Username")
        user_label.setObjectName("fieldLabel")

        self.username_input = PrimeInput()
        self.username_input.setPlaceholderText("Enter your username")
        self.username_input.textChanged.connect(self.clear_errors)

        self.username_error = QLabel("")
        self.username_error.setObjectName("errorLabel")
        self.username_error.hide()

        # Password
        pass_label = QLabel("Password")
        pass_label.setObjectName("fieldLabel")

        password_wrap = QFrame()
        password_layout = QHBoxLayout(password_wrap)
        password_layout.setContentsMargins(0, 0, 0, 0)
        password_layout.setSpacing(0)

        self.password_input = PrimeInput()
        self.password_input.setPlaceholderText("Enter your password")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.textChanged.connect(self.clear_errors)

        password_layout.addWidget(self.password_input)


        self.password_error = QLabel("")
        self.password_error.setObjectName("errorLabel")
        self.password_error.hide()

        # Login button
        self.login_button = PrimeButton(text="Login", height=128)
        self.login_button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.back_button = QPushButton("Back to Live View")
        self.back_button.setObjectName("backButton")
        self.back_button.setCursor(Qt.PointingHandCursor)
        self.back_button.setMinimumHeight(44)

        # Divider
        divider_wrap = QWidget()
        divider_layout = QHBoxLayout(divider_wrap)
        divider_layout.setContentsMargins(0, 0, 0, 0)
        divider_layout.setSpacing(10)

        line_left = QFrame()
        line_left.setObjectName("dividerLine")
        line_left.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        divider_text = QLabel("SECURE LOGIN")
        divider_text.setObjectName("dividerText")
        divider_text.setAlignment(Qt.AlignmentFlag.AlignCenter)

        line_right = QFrame()
        line_right.setObjectName("dividerLine")
        line_right.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        divider_layout.addWidget(line_left)
        divider_layout.addWidget(divider_text)
        divider_layout.addWidget(line_right)

        # Footer
        footer_wrap = QVBoxLayout()
        footer_wrap.setSpacing(6)
        footer_wrap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        version_row = QHBoxLayout()
        version_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_text = QLabel("Version ")
        version_text.setObjectName("versionLabel")
        version_val = QLabel("1.0.0")
        version_val.setObjectName("versionValue")
        version_row.addWidget(version_text)
        version_row.addWidget(version_val)

        copyright_label = QLabel("© 2025 bomn company")
        copyright_label.setObjectName("footerLabel")
        copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        footer_wrap.addLayout(version_row)
        footer_wrap.addWidget(copyright_label)

        card_layout.addWidget(user_label)
        card_layout.addWidget(self.username_input)
        card_layout.addWidget(self.username_error)

        card_layout.addWidget(pass_label)
        card_layout.addWidget(password_wrap)
        card_layout.addWidget(self.password_error)

        card_layout.addSpacing(4)
        card_layout.addWidget(self.login_button)
        card_layout.addWidget(self.back_button)
        card_layout.addSpacing(8)
        card_layout.addWidget(divider_wrap)
        card_layout.addSpacing(6)
        card_layout.addLayout(footer_wrap)

        container_layout.addWidget(self.card, alignment=Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(container)

    def setup_animations(self):
        self.card_anim = QPropertyAnimation(self.card, b"geometry")
        self.card_anim.setDuration(900)
        self.card_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.left_anim = QPropertyAnimation(self.circle_left, b"geometry")
        self.left_anim.setDuration(8000)
        self.left_anim.setLoopCount(-1)
        self.left_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

        self.right_anim = QPropertyAnimation(self.circle_right, b"geometry")
        self.right_anim.setDuration(8000)
        self.right_anim.setLoopCount(-1)
        self.right_anim.setEasingCurve(QEasingCurve.Type.InOutSine)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        w = self.width()
        h = self.height()

        self.circle_left.setGeometry(-220, h - 470, 700, 700)
        self.circle_right.setGeometry(w - 250, -120, 420, 420)

        self.left_anim.stop()
        self.left_anim.setStartValue(QRect(-220, h - 470, 700, 700))
        self.left_anim.setEndValue(QRect(-180, h - 510, 700, 700))
        self.left_anim.start()

        self.right_anim.stop()
        self.right_anim.setStartValue(QRect(w - 250, -120, 420, 420))
        self.right_anim.setEndValue(QRect(w - 290, -80, 420, 420))
        self.right_anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0.0, QColor("#000000"))
        gradient.setColorAt(0.5, QColor("#222222"))
        gradient.setColorAt(1.0, QColor("#000000"))
        painter.fillRect(self.rect(), gradient)

    def clear_errors(self):
        self.username_error.hide()
        self.password_error.hide()

        self.username_input.clear_error()
        self.password_input.clear_error()

    def validate_form(self):
        valid = True
        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        if not username:
            self.username_error.setText("Username is required.")
            self.username_error.show()
            self.username_input.set_error()
            valid = False

        if not password:
            self.password_error.setText("Password is required.")
            self.password_error.show()
            self.password_input.set_error()
            valid = False

        return valid

    def set_loading(self, state: bool):
        self.is_loading = state
        self.username_input.setDisabled(state)
        self.password_input.setDisabled(state)
        self.login_button.setDisabled(state)
        self.back_button.setDisabled(state)

        if state:
            self.login_button.setText("Signing In...")
        else:
            self.login_button.setText("Login")

    def _toast_error(self, summary: str, detail: str = "", life: int = 4200) -> None:
        if hasattr(self, "toast"):
            self.toast.error(summary, detail, life)

    def _handle_back(self):
        if self.is_loading:
            return
        self.back_requested.emit()

    def handle_login(self):
        if self.is_loading:
            return

        self.clear_errors()

        if not self.validate_form():
            return

        username = self.username_input.text().strip()
        password = self.password_input.text().strip()

        self.set_loading(True)
        QTimer.singleShot(0, lambda: self.finish_login(username, password))

    def finish_login(self, username: str, password: str):
        try:
            response = self.auth_service.login({"username": username, "password": password})
            if not isinstance(response, dict):
                self.password_error.setText("Invalid username/password or server unavailable.")
                self.password_error.show()
                return

            token = str(response.get("access_token") or "").strip()
            if not token:
                self.password_error.setText("Login failed. No token returned by server.")
                self.password_error.show()
                return

            # Make token available for all API-backed pages.
            os.environ["AUTH_TOKEN"] = token
            os.environ["ACCESS_TOKEN"] = token
            os.environ["TOKEN"] = token

            self.password_input.clear()
            self.login_success.emit()
        except Exception as e:
            self._toast_error("Login Error", str(e))
        finally:
            self.set_loading(False)

    def reset_form(self):
        self.clear_errors()
        self.password_input.clear()
        self.set_loading(False)
        self.username_input.setFocus()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    font = QFont("Segoe UI", 10)
    app.setFont(font)

    window = LoginWindow()
    install_english_digit_support(window)
    window.setWindowFlags(Qt.FramelessWindowHint)
    window.showFullScreen()
    sys.exit(app.exec())
