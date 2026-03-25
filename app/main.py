import sys
import os
import importlib
import inspect
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QApplication,
    QWidget,
    QVBoxLayout,
    QStackedWidget,
    QLabel,
    QFrame,
    QMainWindow,
    QDialog,
    QPushButton,
)
from PySide6.QtGui import QIcon

from app.ui.header import AppHeader
from app.utils.qt_digits import install_english_digit_support
from app.utils.env import load_runtime_env
from app.ui.virtual_keyboard import install_virtual_keyboard, set_virtual_keyboard_toggle_visible
from app.ui.toast import PrimeToastHost

load_runtime_env()

from app.views.auth.live_view import StartupLiveViewPage
from app.views.auth.login import LoginWindow
from app.views.home.control_panel import ControlPanel, CONTROL_PANEL_TABS

Base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "./"))
Logo_path = os.path.join(Base_dir, "resources/Logo.svg")
Icons_dir = os.path.join(Base_dir, "resources", "icons")


def _icon(name: str) -> str:
    return os.path.join(Icons_dir, name)


def _resolve_svg_icon(svg_icon: str) -> str:
    if not svg_icon:
        return ""
    candidates = [svg_icon]
    if not os.path.isabs(svg_icon):
        candidates.append(os.path.abspath(svg_icon))
        candidates.append(os.path.abspath(os.path.join(Base_dir, svg_icon)))
        candidates.append(os.path.abspath(os.path.join(Base_dir, svg_icon.lstrip("/"))))
    basename = os.path.basename(svg_icon)
    if basename:
        candidates.append(os.path.join(Icons_dir, basename))
    for candidate in candidates:
        if os.path.isfile(candidate):
            return candidate
    return ""


_EXTRA_ROUTE_INFO = {
    "/settings/monitor": {"name": "Monitor", "icon": "📊", "svg_icon": _icon("monitor.svg")},
    "/face/view": {"name": "Faces View", "icon": "👥", "svg_icon": _icon("faces.svg")},
    "/device/body-cam": {"name": "Bodycam Devices", "icon": "📱", "svg_icon": _icon("bodycam.svg")},
}


_ROUTE_MODULE_IMPORTS = {
    "/camera/playback": "app.views.home.stream.playback",
    "/user/profile": "app.views.home.user.profile",
    "/user/users": "app.views.home.user.users",
    "/user/roles": "app.views.home.user.roles",
    "/user/department": "app.views.home.user.department",
    "/device/clients": "app.views.home.devices.clients",
    "/device/access-control": "app.views.home.devices.access_controls",
    "/log/user": "app.views.home.logs.user_log",
    "/log/client": "app.views.home.logs.client_log",
    "/log/camera": "app.views.home.logs.camera_log",
    "/clients/activation": "app.views.home.activation",
    "/system/update": "app.views.home.update",
    "/system/settings": "app.views.home.settings",
    "/browser": "app.views.home.browser",
    "/system/terminal": "app.views.home.shell",
    "/search/lpr": "app.views.lpr.search",
    "/search/lpr/repeated": "app.views.lpr.repeated",
    "/search/lprmap": "app.views.lpr.monitor_lpr",
    "/lpr/blacklist": "app.views.lpr.blacklist",
    "/lpr/whitelist": "app.views.lpr.whitelist",
    "/report/lpr": "app.views.lpr.report",
    "/search/face": "app.views.face.search",
    "/search/facemap": "app.views.face.monitor_face",
    "/face/blacklist": "app.views.face.blacklist",
    "/face/whitelist": "app.views.face.whitelist",
    "/report/face": "app.views.face.report",
    "/report/face_count": "app.views.face.count_report",
    "/face/view": "app.views.auth.live_view",
}

# Build a flat path → {name, icon} lookup from CONTROL_PANEL_TABS
def _build_path_info() -> dict:
    info: dict[str, dict] = {}
    for tab in CONTROL_PANEL_TABS:
        children = tab.get("children", [])
        if children:
            for child in children:
                p = child.get("path", "")
                if p:
                    info[p] = {
                        "name": child["name"],
                        "icon": tab.get("icon", ""),
                        "svg_icon": _resolve_svg_icon(child.get("svg_icon") or tab.get("svg_icon", "")),
                    }
        else:
            p = tab.get("path", "")
            if p:
                info[p] = {
                    "name": tab["name"],
                    "icon": tab.get("icon", ""),
                    "svg_icon": _resolve_svg_icon(tab.get("svg_icon", "")),
                }
    for path, meta in _EXTRA_ROUTE_INFO.items():
        merged = dict(meta)
        merged["svg_icon"] = _resolve_svg_icon(merged.get("svg_icon", ""))
        info.setdefault(path, merged)
    return info

_PATH_INFO = _build_path_info()


_GROUPED_TAB_META = {
    "/search/lpr": {
        "paths": {
            "/search/lpr",
            "/search/lpr/repeated",
            "/search/lprmap",
            "/search/face",
            "/search/facemap",
        },
        "name": "Search",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("search.svg")),
    },
    "/report/lpr": {
        "paths": {
            "/report/lpr",
            "/report/face",
            "/report/face_count",
        },
        "name": "Report",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("report.svg")),
    },
    "/user/profile": {
        "paths": {
            "/user/profile",
            "/user/users",
            "/user/roles",
            "/user/department",
        },
        "name": "User Management",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("user_managment.svg")),
    },
    "/device/clients": {
        "paths": {
            "/device/clients",
            "/device/cameras",
            "/device/gps",
            "/device/access-control",
            "/device/body-cam",
        },
        "name": "Device Management",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("devices.svg")),
    },
    "/log/user": {
        "paths": {
            "/log/user",
            "/log/client",
            "/log/camera",
        },
        "name": "Activity Log",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("activity_logs.svg")),
    },
    "/lpr/blacklist": {
        "paths": {
            "/lpr/blacklist",
            "/lpr/whitelist",
            "/face/blacklist",
            "/face/whitelist",
        },
        "name": "List Management",
        "icon": "",
        "svg_icon": _resolve_svg_icon(_icon("list_management.svg")),
    },
}


def _normalize_tab_path(path: str) -> str:
    for canonical_path, meta in _GROUPED_TAB_META.items():
        if path in meta["paths"]:
            return canonical_path
    return path


def _tab_meta_for_path(path: str) -> dict:
    normalized_path = _normalize_tab_path(path)
    grouped_meta = _GROUPED_TAB_META.get(normalized_path)
    if grouped_meta is not None:
        meta = {k: v for k, v in grouped_meta.items() if k != "paths"}
    else:
        meta = dict(_PATH_INFO.get(path, {}))
    meta["path"] = normalized_path
    return meta


class RouteScreen(QWidget):
    def __init__(self, name: str, path: str, details: str = ""):
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)

        panel = QFrame(self)
        panel.setObjectName("routePanel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(28, 24, 28, 24)
        panel_layout.setSpacing(10)

        title = QLabel(name)
        title.setObjectName("routeTitle")
        subtitle = QLabel(path)
        subtitle.setObjectName("routePath")

        panel_layout.addWidget(title)
        panel_layout.addWidget(subtitle)
        if details:
            body = QLabel(details)
            body.setObjectName("routeBody")
            body.setWordWrap(True)
            panel_layout.addWidget(body)

        root.addWidget(panel)
        root.addStretch(1)

        self.setStyleSheet(
            """
            QWidget {
                background: #0f1217;
                color: #e5e7eb;
            }
            QFrame#routePanel {
                background: #171b22;
                border: 1px solid #2a3140;
                border-radius: 14px;
            }
            QLabel#routeTitle {
                font-size: 24px;
                font-weight: 700;
                color: #f8fafc;
            }
            QLabel#routePath {
                font-size: 13px;
                color: #94a3b8;
                padding-bottom: 8px;
            }
            QLabel#routeBody {
                font-size: 14px;
                color: #cbd5e1;
                line-height: 1.45em;
            }
            """
        )


class MainWindow(QWidget):
    logout_requested = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cityguard")
        self._live_view_widget = None

        # ── layout ────────────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Global header — always visible
        self.header = AppHeader(self)
        root.addWidget(self.header)

        # Stacked content area
        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)

        # ── views ─────────────────────────────────────────────────────────────
        self.control_panel = ControlPanel()
        self.stack.addWidget(self.control_panel)   # index 0 — home "/"

        # Route → stacked-widget index
        self._view_index: dict[str, int] = {"/": 0}
        self._view_factories: dict[str, Callable[[], QWidget]] = {
            "/device/cameras": self._build_camera_page,
            "/device/clients": self._build_clients_page,
            "/stream/live": self._build_live_view_page,
        }
        for route, module_path in _ROUTE_MODULE_IMPORTS.items():
            self._view_factories.setdefault(route, self._make_module_factory(route, module_path))

        # ── wiring ────────────────────────────────────────────────────────────
        # Card click on control panel → add tab in header + show view
        self.control_panel.navigate.connect(self._on_card_navigate)

        # Header tab clicks and right-side quick actions share the same signal.
        self.header.navigate.connect(self._on_header_navigate)

        # Logout
        self.header.logout_requested.connect(self._on_logout)

        # Default active tab/view
        self.stack.setCurrentIndex(0)
        self.header.set_current("/")

    # ── navigation ────────────────────────────────────────────────────────────
    def _on_card_navigate(self, path: str):
        """Control-panel card was clicked — open/activate a tab then show view."""
        self._activate_route(path)
        self._show_view(path)

    def _on_header_navigate(self, path: str):
        """Header emitted navigate — just switch the stacked view."""
        if path == "/":
            self._show_view("/")
            return
        self._activate_route(path)
        self._show_view(path)

    def _on_logout(self):
        self.reset_to_home()
        self.logout_requested.emit()

    def reset_to_home(self):
        self._show_view("/")
        self.header.set_current("/")

    def navigate_to(self, path: str):
        if path == "/":
            self.reset_to_home()
            return
        self._activate_route(path)
        self._show_view(path)

    def _show_view(self, path: str):
        """Switch the stack to the view for *path*, creating route screens lazily."""
        if path != "/" and path not in self._view_index:
            self._ensure_view(path)

        if path in self._view_index:
            self.stack.setCurrentIndex(self._view_index[path])
        else:
            # View not yet registered — fall back to control-panel home
            self.stack.setCurrentIndex(0)

        if path != "/stream/live":
            self._ensure_tv_mode_off()
            self._deactivate_live_view_overlays()
            self._destroy_live_view()

    def _ensure_tv_mode_off(self):
        if self._live_view_widget is not None:
            try:
                self._live_view_widget.set_tv_mode(False)
            except Exception:
                pass
        self._on_live_tv_mode_changed(False)

    def _deactivate_live_view_overlays(self):
        if self._live_view_widget is None:
            return
        try:
            self._live_view_widget.deactivate_overlays()
        except Exception:
            pass

    def _on_live_tv_mode_changed(self, enabled: bool):
        self.header.setVisible(not enabled)
        set_virtual_keyboard_toggle_visible(not enabled)

    # ── helpers ───────────────────────────────────────────────────────────────
    def register_view(self, path: str, widget: QWidget):
        """Register a view widget for a route path (call before showing)."""
        idx = self.stack.addWidget(widget)
        self._view_index[path] = idx

    def _destroy_live_view(self):
        live_view = self._live_view_widget
        live_view_index = self._view_index.get("/stream/live")
        if live_view is None or live_view_index is None:
            return

        try:
            live_view.set_tv_mode(False)
        except Exception:
            pass
        try:
            live_view.deactivate_overlays()
        except Exception:
            pass

        self.stack.removeWidget(live_view)
        for route, index in list(self._view_index.items()):
            if index > live_view_index:
                self._view_index[route] = index - 1
        self._view_index.pop("/stream/live", None)
        live_view.deleteLater()
        self._live_view_widget = None
        self._on_live_tv_mode_changed(False)

    def _activate_route(self, path: str):
        meta = _tab_meta_for_path(path)
        name = meta.get("name", self._label_from_path(path))
        icon = meta.get("icon", "")
        svg_icon = meta.get("svg_icon", "")
        self.header.add_tab(name, meta.get("path", path), icon, svg_icon)
        self.header.set_current(path)

    def _ensure_view(self, path: str):
        if path in self._view_index or path == "/":
            return
        self.register_view(path, self._create_view_for_path(path))

    def _create_view_for_path(self, path: str) -> QWidget:
        meta = _PATH_INFO.get(path, {})
        name = meta.get("name", self._label_from_path(path))
        factory = self._view_factories.get(path)
        if not factory:
            return RouteScreen(
                name=name,
                path=path,
                details="This route is registered and navigable. Build out this screen when ready.",
            )
        try:
            return factory()
        except Exception as exc:
            return RouteScreen(
                name=name,
                path=path,
                details=f"Screen failed to initialize: {exc}",
            )

    def _label_from_path(self, path: str) -> str:
        parts = [p for p in path.split("/") if p]
        if not parts:
            return "Control Panel"
        return " ".join(part.replace("-", " ").title() for part in parts)

    def _make_module_factory(self, path: str, module_path: str) -> Callable[[], QWidget]:
        return lambda p=path, m=module_path: self._build_module_route_page(p, m)

    def _build_module_route_page(self, path: str, module_path: str) -> QWidget:
        meta = _PATH_INFO.get(path, {})
        name = meta.get("name", self._label_from_path(path))
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            return RouteScreen(
                name=name,
                path=path,
                details=f"Screen module is not ready yet ({module_path}). {exc}",
            )

        view_cls = self._pick_widget_class(module)
        if view_cls is None:
            return RouteScreen(
                name=name,
                path=path,
                details=(
                    f"Screen module loaded ({module_path}) but no root QWidget class was found. "
                    "Add one page class and this route will render it automatically."
                ),
            )

        try:
            page = view_cls()
        except TypeError as exc:
            return RouteScreen(
                name=name,
                path=path,
                details=f"{view_cls.__name__} needs constructor args: {exc}",
            )
        except Exception as exc:
            return RouteScreen(
                name=name,
                path=path,
                details=f"{view_cls.__name__} failed to initialize: {exc}",
            )

        if isinstance(page, QMainWindow):
            page.setWindowFlags(Qt.WindowType.Widget)
        navigate_signal = getattr(page, "navigate", None)
        if navigate_signal is None and isinstance(page, QMainWindow):
            central = page.centralWidget()
            navigate_signal = getattr(central, "navigate", None) if central is not None else None
        if navigate_signal is not None and hasattr(navigate_signal, "connect"):
            try:
                navigate_signal.connect(self._on_card_navigate)
            except Exception:
                pass
        return page

    def _pick_widget_class(self, module):
        candidates = []
        for _, obj in inspect.getmembers(module, inspect.isclass):
            if obj.__module__ != module.__name__:
                continue
            if not issubclass(obj, QWidget):
                continue
            if issubclass(obj, (QDialog, QLabel, QPushButton, QFrame)):
                continue

            try:
                sig = inspect.signature(obj)
            except (TypeError, ValueError):
                continue
            required = [
                p for p in sig.parameters.values()
                if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
                and p.default is inspect.Signature.empty
                and p.name != "self"
            ]
            if required:
                continue

            name = obj.__name__.lower()
            score = 0
            if isinstance(obj, type) and issubclass(obj, QMainWindow):
                score += 60
            if any(k in name for k in ("page", "screen", "dashboard", "window", "view")):
                score += 40
            if name in {"mainwindow", "mainpage", "mainscreen"}:
                score += 10
            if name in {"floatingcircle", "glasscard", "recbadge", "cameraoverlay", "videowidget"}:
                score -= 100
            candidates.append((score, obj.__name__, obj))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return candidates[0][2]

    def _build_camera_page(self) -> QWidget:
        from app.services.auth.auth_service import AuthService
        from app.services.home.devices.access_control_service import (
            AccessControlService,
        )
        from app.services.home.devices.camera_service import CameraService
        from app.services.home.devices.camera_type_service import (
            CameraTypeService,
        )
        from app.services.home.devices.client_service import ClientService
        from app.store.auth import AuthStore
        from app.store.home.devices.access_control_store import (
            AccessControlStore,
        )
        from app.store.home.devices.camera_store import CameraStore
        from app.store.home.devices.camera_type_store import CameraTypeStore
        from app.store.home.devices.client_store import ClientStore
        from app.store.home.user.department_store import DepartmentStore
        from app.views.home.devices.cameras import CameraPage

        auth_service = AuthService()
        client_service = ClientService()
        camera_type_service = CameraTypeService()
        access_control_service = AccessControlService()
        camera_service = CameraService()

        auth_store = AuthStore(auth_service)
        client_store = ClientStore(client_service)
        camera_type_store = CameraTypeStore(camera_type_service)
        access_control_store = AccessControlStore(access_control_service)
        department_store = DepartmentStore(camera_service)
        camera_store = CameraStore(camera_service, department_store)

        auth_store.load()
        client_store.load()
        camera_type_store.load()
        access_control_store.load()
        department_store.get_camera_for_user(
            auth_store.current_user.department_id if auth_store.current_user else None
        )

        page = CameraPage(
            auth_store,
            client_store,
            camera_type_store,
            access_control_store,
            department_store,
            camera_store,
        )
        page.navigate.connect(self._on_card_navigate)
        return page

    def _build_clients_page(self) -> QWidget:
        from app.views.home.devices.clients import ClientPage

        page = ClientPage()
        page.navigate.connect(self._on_card_navigate)
        return page

    def _build_live_view_page(self) -> QWidget:
        from app.views.home.stream.live_view import CameraDashboard

        live_view = CameraDashboard()
        live_view.setWindowFlags(Qt.WindowType.Widget)
        live_view.tvModeChanged.connect(self._on_live_tv_mode_changed)
        self._live_view_widget = live_view
        return live_view


class RootWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("City Guard")
        self.toast = PrimeToastHost(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.stack = QStackedWidget(self)
        root.addWidget(self.stack, 1)

        self.startup_live_page = None
        self.login_page = LoginWindow()
        self.dashboard_page = MainWindow()

        self.stack.addWidget(self.login_page)
        self.stack.addWidget(self.dashboard_page)
        self.stack.setCurrentWidget(self._ensure_startup_live_page())

        self.login_page.login_success.connect(self._on_login_success)
        self.login_page.back_requested.connect(self._show_startup_live_page)
        self.dashboard_page.logout_requested.connect(self._on_logout_requested)

    def _ensure_startup_live_page(self):
        if self.startup_live_page is not None:
            return self.startup_live_page

        self.startup_live_page = StartupLiveViewPage()
        self.startup_live_page.loginRequested.connect(self._show_login_page)
        self.startup_live_page.tvModeChanged.connect(self._on_startup_live_tv_mode_changed)
        self.stack.insertWidget(0, self.startup_live_page)
        return self.startup_live_page

    def _dispose_startup_live_page(self):
        page = self.startup_live_page
        if page is None:
            return
        self._deactivate_startup_live_overlays()
        self.stack.removeWidget(page)
        page.deleteLater()
        self.startup_live_page = None

    def _deactivate_startup_live_overlays(self):
        if self.startup_live_page is None:
            return
        try:
            self.startup_live_page.set_tv_mode(False)
        except Exception:
            pass
        try:
            self.startup_live_page.deactivate_overlays()
        except Exception:
            pass

    def _show_login_page(self):
        self._dispose_startup_live_page()
        self.login_page.reset_form()
        self.stack.setCurrentWidget(self.login_page)
        set_virtual_keyboard_toggle_visible(True)

    def _show_startup_live_page(self):
        self.login_page.reset_form()
        page = self._ensure_startup_live_page()
        self.stack.setCurrentWidget(page)
        self._on_startup_live_tv_mode_changed(bool(getattr(page, "is_tv_mode", False)))

    def _on_login_success(self):
        self._dispose_startup_live_page()
        self.dashboard_page.reset_to_home()
        self.stack.setCurrentWidget(self.dashboard_page)
        set_virtual_keyboard_toggle_visible(True)
        self.toast.success("Login Success", "Welcome to City Guard.")

    def _on_logout_requested(self):
        os.environ.pop("AUTH_TOKEN", None)
        os.environ.pop("ACCESS_TOKEN", None)
        os.environ.pop("TOKEN", None)
        self._show_startup_live_page()

    def _on_startup_live_tv_mode_changed(self, enabled: bool):
        if self.startup_live_page is not None and self.stack.currentWidget() is self.startup_live_page:
            set_virtual_keyboard_toggle_visible(not enabled)


def main():
    load_runtime_env()
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon(Logo_path))

    window = RootWindow()
    install_english_digit_support(window)
    install_virtual_keyboard(window)
    window.setWindowFlags(Qt.FramelessWindowHint)
    window.showFullScreen()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
