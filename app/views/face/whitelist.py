from __future__ import annotations

import base64
import os
from typing import Dict, List, Optional, Type

from PySide6.QtCore import QSize, QUrl, Qt, Signal
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QDialog,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedLayout,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from app.models.face.whitelist import FaceWhitelistEntry, FaceWhitelistPayload, FaceWhitelistTemplate
from app.services.auth.auth_service import AuthService
from app.services.home.devices.camera_service import CameraService
from app.services.home.face_whitelist_service import FaceWhitelistService, LowSimilarityError
from app.store.auth import AuthStore
from app.store.home.face.face_whitelist_store import FaceWhitelistStore
from app.store.home.user.department_store import DepartmentStore as CameraDepartmentStore
from app.ui.button import PrimeButton
from app.ui.table import PrimeDataTable, PrimeTableColumn
from app.ui.toast import PrimeToastHost
from app.views.watchlist_shared import WATCHLIST_SIDEBAR_STYLES, WatchlistSidebar


_ICONS_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../resources/icons")
)


def _icon_path(name: str) -> str:
    return os.path.join(_ICONS_DIR, name)


_DIALOG_BUTTON_QSS = """
QPushButton {
    background: #2b3340;
    border: 1px solid #425062;
    border-radius: 8px;
    color: #f8fafc;
    padding: 7px 14px;
    font-weight: 600;
    min-height: 18px;
}
QPushButton:hover {
    background: #35507f;
    border-color: #4d76bb;
}
QPushButton:disabled {
    background: #20242b;
    color: #7f8a99;
    border-color: #313844;
}
"""


class RemoteImageLabel(QLabel):
    def __init__(
        self,
        net: QNetworkAccessManager,
        fallback_text: str = "No Image",
        auth_token: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._net = net
        self._reply: Optional[QNetworkReply] = None
        self._original = QPixmap()
        self._image_url = ""
        self._fallback_text = fallback_text
        self._auth_token = auth_token.strip()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setText(self._fallback_text)
        self.setScaledContents(False)

    def set_auth_token(self, token: str) -> None:
        self._auth_token = str(token or "").strip()

    def set_image_url(self, url: str) -> None:
        self._abort_reply()
        self._original = QPixmap()
        self._image_url = str(url or "").strip()
        if not self._image_url:
            self.setPixmap(QPixmap())
            self.setText(self._fallback_text)
            return
        if self._image_url.startswith("data:image/"):
            self._load_data_url(self._image_url)
            return
        self.setPixmap(QPixmap())
        self.setText("Loading...")
        if self.isVisible():
            self._start_request()

    def showEvent(self, event) -> None:  # type: ignore[override]
        super().showEvent(event)
        if self._reply is None and self._original.isNull() and self._image_url and not self._image_url.startswith("data:image/"):
            self._start_request()

    def hideEvent(self, event) -> None:  # type: ignore[override]
        super().hideEvent(event)
        if self._reply is not None:
            self._abort_reply()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._apply_scaled()

    def _load_data_url(self, data_url: str) -> None:
        try:
            _, encoded = data_url.split(",", 1)
            payload = base64.b64decode(encoded)
        except Exception:
            self.setText(self._fallback_text)
            return
        pix = QPixmap()
        if not pix.loadFromData(payload):
            self.setText(self._fallback_text)
            return
        self._original = pix
        self._apply_scaled()

    def _start_request(self) -> None:
        if not self._image_url:
            return
        request = QNetworkRequest(QUrl(self._image_url))
        request.setRawHeader(b"Accept", b"image/*")
        if self._auth_token:
            request.setRawHeader(b"Authorization", f"Bearer {self._auth_token}".encode("utf-8"))
        self._reply = self._net.get(request)
        self._reply.finished.connect(self._on_done)

    def _abort_reply(self) -> None:
        if self._reply is None:
            return
        try:
            self._reply.abort()
        except Exception:
            pass
        self._reply.deleteLater()
        self._reply = None

    def _on_done(self) -> None:
        reply = self._reply
        self._reply = None
        if reply is None:
            return
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                self.setText(self._fallback_text)
                return
            pix = QPixmap()
            if not pix.loadFromData(bytes(reply.readAll())):
                self.setText(self._fallback_text)
                return
            self._original = pix
            self._apply_scaled()
        finally:
            reply.deleteLater()

    def _apply_scaled(self) -> None:
        if self._original.isNull():
            return
        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            return
        scaled = self._original.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(scaled)
        self.setText("")


class AddImageDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._image_path = ""
        self._person_name = ""
        self._person_id = ""
        self.setWindowTitle("Add Image")
        self.resize(520, 440)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.info_label = QLabel("Person: -")
        self.info_label.setObjectName("faceDialogInfo")
        root.addWidget(self.info_label)

        self.count_label = QLabel("Current templates: 0")
        self.count_label.setObjectName("faceDialogHint")
        root.addWidget(self.count_label)

        self.preview = QLabel("No image selected")
        self.preview.setObjectName("faceUploadPreview")
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setMinimumHeight(220)
        root.addWidget(self.preview)

        picker_actions = QHBoxLayout()
        picker_actions.setSpacing(8)
        root.addLayout(picker_actions)

        self.choose_btn = QPushButton("Choose Image")
        self.choose_btn.clicked.connect(self._pick_image)
        picker_actions.addWidget(self.choose_btn)

        self.clear_btn = QPushButton("Clear")
        self.clear_btn.clicked.connect(self.clear_selected_image)
        picker_actions.addWidget(self.clear_btn)

        picker_actions.addStretch(1)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        root.addLayout(footer)

        self.close_btn = QPushButton("Done")
        self.close_btn.clicked.connect(self.reject)
        footer.addWidget(self.close_btn)

        self.submit_btn = QPushButton("Add Image")
        self.submit_btn.clicked.connect(self._submit)
        footer.addWidget(self.submit_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b21;
                color: #eef2f8;
            }
            QLabel#faceDialogInfo {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#faceDialogHint {
                color: #93a1b6;
                font-size: 12px;
            }
            QLabel#faceUploadPreview {
                background: #11161c;
                border: 1px dashed #3b4a5e;
                border-radius: 16px;
                color: #93a1b6;
                font-size: 13px;
            }
            """
            + _DIALOG_BUTTON_QSS
        )

    def set_person(self, entry: FaceWhitelistEntry, template_count: int) -> None:
        self._person_name = entry.name or "Unknown"
        self._person_id = entry.identifier
        self.info_label.setText(f"Person: {self._person_name} | ID: {self._person_id}")
        self.count_label.setText(f"Current templates: {template_count}")
        self.clear_selected_image()

    def selected_image_path(self) -> str:
        return self._image_path

    def clear_selected_image(self) -> None:
        self._image_path = ""
        self.preview.setPixmap(QPixmap())
        self.preview.setText("No image selected")

    def set_selected_image(self, image_path: str) -> None:
        self._image_path = image_path
        pix = QPixmap(image_path)
        if pix.isNull():
            self.preview.setPixmap(QPixmap())
            self.preview.setText(os.path.basename(image_path) or "Selected image")
            return
        self.preview.setPixmap(
            pix.scaled(
                self.preview.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview.setText("")

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Face Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self.set_selected_image(path)

    def _submit(self) -> None:
        if not self._image_path:
            QMessageBox.warning(self, "Add Image", "Choose an image first.")
            return
        self.accept()

class LowSimilarityDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Image doesn't match")
        self.resize(420, 220)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        self.message_label = QLabel("")
        self.message_label.setWordWrap(True)
        self.message_label.setObjectName("faceLowSimTitle")
        root.addWidget(self.message_label)

        self.detail_label = QLabel("")
        self.detail_label.setWordWrap(True)
        self.detail_label.setObjectName("faceLowSimDetail")
        root.addWidget(self.detail_label)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        root.addLayout(actions)

        self.retry_btn = QPushButton("Try Another Image")
        self.retry_btn.clicked.connect(self.reject)
        actions.addWidget(self.retry_btn)

        self.create_btn = QPushButton("Create New Record")
        self.create_btn.clicked.connect(self.accept)
        actions.addWidget(self.create_btn)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b21;
                color: #eef2f8;
            }
            QLabel#faceLowSimTitle {
                color: #f8fafc;
                font-size: 15px;
                font-weight: 700;
            }
            QLabel#faceLowSimDetail {
                color: #93a1b6;
                font-size: 12px;
            }
            """
            + _DIALOG_BUTTON_QSS
        )

    def set_error(self, error: LowSimilarityError) -> None:
        self.message_label.setText(error.message or "New image does not match this person.")
        self.detail_label.setText(
            f"Similarity {error.similarity:.2f}% < required {error.required_similarity:.2f}%."
        )


class PersonFormDialog(QFrame):
    submitted = Signal()
    cancelled = Signal()
    validation_error = Signal(str)

    def __init__(
        self,
        camera_options: List[dict],
        entry: Optional[FaceWhitelistEntry] = None,
        prefill_name: str = "",
        prefill_image_path: str = "",
        title_text: str = "Face Whitelist",
        create_hint_text: str = "Create a whitelist person and assign one or more cameras.",
        edit_hint_text: str = "Update whitelist person details. Use the image actions in the table to manage templates.",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._entry = entry
        self._selected_image_path = ""
        self._camera_options = list(camera_options)
        self._title_text = title_text
        self._create_hint_text = create_hint_text
        self._edit_hint_text = edit_hint_text
        self.setObjectName("faceFormCard")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMinimumWidth(520)
        self.setMaximumWidth(560)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        root.addLayout(title_row)

        self.title_label = QLabel(self._title_text)
        self.title_label.setObjectName("faceEditorTitle")
        title_row.addWidget(self.title_label, 1)

        close_btn = QToolButton()
        close_btn.setObjectName("faceFormCloseButton")
        close_btn.setText("×")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(lambda: self.cancelled.emit())
        title_row.addWidget(close_btn)

        hint_text = self._edit_hint_text if entry is not None else self._create_hint_text
        self.hint_label = QLabel(hint_text)
        self.hint_label.setObjectName("faceEditorHint")
        self.hint_label.setWordWrap(True)
        root.addWidget(self.hint_label)

        self.preview_label = QLabel("Choose a primary face image")
        self.preview_label.setObjectName("faceUploadPreview")
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFixedHeight(180)
        root.addWidget(self.preview_label)

        image_actions = QHBoxLayout()
        image_actions.setSpacing(8)
        root.addLayout(image_actions)

        self.choose_image_btn = QPushButton("Choose Image")
        self.choose_image_btn.clicked.connect(self._pick_image)
        image_actions.addWidget(self.choose_image_btn)

        self.clear_image_btn = QPushButton("Clear")
        self.clear_image_btn.clicked.connect(self._clear_image)
        image_actions.addWidget(self.clear_image_btn)

        self.edit_notice = QLabel("Editing updates details only. Add new face images from the table actions.")
        self.edit_notice.setObjectName("faceEditorMinor")
        self.edit_notice.setWordWrap(True)
        self.edit_notice.setVisible(entry is not None)
        root.addWidget(self.edit_notice)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, 1)

        body = QWidget()
        scroll.setWidget(body)

        form = QVBoxLayout(body)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(12)

        self.name_edit = self._line_edit("Full name")
        form.addWidget(self._field_block("Name", self.name_edit))

        top_grid = QGridLayout()
        top_grid.setContentsMargins(0, 0, 0, 0)
        top_grid.setHorizontalSpacing(10)
        top_grid.setVerticalSpacing(12)
        form.addLayout(top_grid)

        self.face_color_edit = self._line_edit("Face color")
        top_grid.addWidget(self._field_block("Face Color", self.face_color_edit), 0, 0)

        self.hair_color_edit = self._line_edit("Hair color")
        top_grid.addWidget(self._field_block("Hair Color", self.hair_color_edit), 0, 1)

        self.age_spin = QSpinBox()
        self.age_spin.setRange(0, 150)
        self.age_spin.setSpecialValueText("Unset")
        self.age_spin.setValue(0)
        top_grid.addWidget(self._field_block("Age", self.age_spin), 1, 0)

        self.gender_select = QComboBox()
        self.gender_select.addItem("Unset", "")
        self.gender_select.addItem("Male", "Male")
        self.gender_select.addItem("Female", "Female")
        top_grid.addWidget(self._field_block("Gender", self.gender_select), 1, 1)

        self.match_spin = QDoubleSpinBox()
        self.match_spin.setRange(0.0, 100.0)
        self.match_spin.setDecimals(2)
        self.match_spin.setSuffix(" %")
        self.match_spin.setSingleStep(1.0)
        self.match_spin.setValue(60.0)
        form.addWidget(self._field_block("Match Threshold", self.match_spin))

        self.camera_select = QListWidget()
        self.camera_select.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.camera_select.setMinimumHeight(132)
        self.camera_select.setMaximumHeight(180)
        self.camera_select.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.camera_select.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.camera_select.setUniformItemSizes(True)
        self._load_camera_items()
        form.addWidget(self._field_block("Cameras", self.camera_select))

        self.note_edit = QTextEdit()
        self.note_edit.setMinimumHeight(88)
        form.addWidget(self._field_block("Notes", self.note_edit))

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        root.addLayout(buttons)

        reset_btn = QPushButton("Reset")
        reset_btn.clicked.connect(self._reset_to_initial_state)
        buttons.addWidget(reset_btn)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(lambda: self.cancelled.emit())
        buttons.addWidget(cancel_btn)

        self.save_btn = QPushButton("Update Details" if entry is not None else "Save Person")
        self.save_btn.clicked.connect(self._submit)
        buttons.addWidget(self.save_btn)

        self.setStyleSheet(
            """
            QFrame#faceFormCard {
                background: #171b21;
                color: #eef2f8;
                border: 1px solid #2b3340;
                border-radius: 20px;
            }
            QLabel#faceEditorTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QToolButton#faceFormCloseButton {
                background: #1f2630;
                border: 1px solid #344154;
                border-radius: 14px;
                color: #f8fafc;
                font-size: 18px;
                font-weight: 700;
                min-width: 28px;
                max-width: 28px;
                min-height: 28px;
                max-height: 28px;
            }
            QToolButton#faceFormCloseButton:hover {
                background: #2f3c4d;
                border-color: #4d76bb;
            }
            QLabel#faceEditorHint {
                color: #93a1b6;
                font-size: 13px;
            }
            QLabel#faceEditorMinor {
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(96, 165, 250, 0.22);
                border-radius: 12px;
                color: #bfdbfe;
                padding: 10px 12px;
                font-size: 12px;
            }
            QLabel#faceFieldLabel {
                color: #d8e1ee;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#faceUploadPreview {
                background: #0f141a;
                border: 1px dashed #38506d;
                border-radius: 16px;
                color: #93a1b6;
                font-size: 13px;
            }
            QLineEdit#faceTextInput,
            QTextEdit,
            QComboBox,
            QListWidget,
            QSpinBox,
            QDoubleSpinBox {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
                min-height: 24px;
            }
            QListWidget::item {
                padding: 6px 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #35507f;
                color: #f8fafc;
            }
            """
            + _DIALOG_BUTTON_QSS
        )

        self.configure(
            camera_options=camera_options,
            entry=entry,
            prefill_name=prefill_name,
            prefill_image_path=prefill_image_path,
        )

    def _line_edit(self, placeholder: str) -> QLineEdit:
        field = QLineEdit()
        field.setObjectName("faceTextInput")
        field.setPlaceholderText(placeholder)
        return field

    def _field_block(self, label_text: str, field: QWidget) -> QWidget:
        wrapper = QWidget()
        layout = QVBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setObjectName("faceFieldLabel")
        layout.addWidget(label)
        layout.addWidget(field)
        return wrapper

    def configure(
        self,
        camera_options: List[dict],
        entry: Optional[FaceWhitelistEntry] = None,
        prefill_name: str = "",
        prefill_image_path: str = "",
        title_text: Optional[str] = None,
        create_hint_text: Optional[str] = None,
        edit_hint_text: Optional[str] = None,
    ) -> None:
        self._entry = entry
        self._camera_options = list(camera_options)
        if title_text is not None:
            self._title_text = title_text
        if create_hint_text is not None:
            self._create_hint_text = create_hint_text
        if edit_hint_text is not None:
            self._edit_hint_text = edit_hint_text
        self._load_camera_items()

        is_edit = entry is not None
        self.title_label.setText(self._title_text)
        self.hint_label.setText(self._edit_hint_text if is_edit else self._create_hint_text)
        self.edit_notice.setVisible(is_edit)
        self.save_btn.setText("Update Details" if is_edit else "Save Person")

        if is_edit and entry is not None:
            self._apply_entry(entry)
        else:
            self._apply_create_defaults(prefill_name=prefill_name, prefill_image_path=prefill_image_path)

        self._initial_payload = self.payload()
        self._initial_image_path = self._selected_image_path

    def _apply_create_defaults(self, prefill_name: str = "", prefill_image_path: str = "") -> None:
        self.choose_image_btn.setEnabled(True)
        self.clear_image_btn.setEnabled(True)
        self.name_edit.clear()
        self.face_color_edit.clear()
        self.hair_color_edit.clear()
        self.age_spin.setValue(0)
        self._set_gender_value(None)
        self.match_spin.setValue(60.0)
        self._set_selected_camera_ids([])
        self.note_edit.clear()
        self._clear_image()
        if prefill_name:
            self.name_edit.setText(prefill_name)
        if prefill_image_path:
            self._set_image(prefill_image_path)

    def _load_camera_items(self) -> None:
        self.camera_select.clear()
        for option in self._camera_options:
            camera_id = option.get("value")
            if camera_id is None:
                continue
            try:
                normalized_id = int(camera_id)
            except (TypeError, ValueError):
                continue
            label = str(option.get("label") or camera_id).strip()
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, normalized_id)
            self.camera_select.addItem(item)

    def _set_gender_value(self, value: Optional[str]) -> None:
        target = str(value or "").strip()
        index = self.gender_select.findData(target)
        self.gender_select.setCurrentIndex(index if index >= 0 else 0)

    def _gender_value(self) -> str:
        return str(self.gender_select.currentData() or "").strip()

    def _set_selected_camera_ids(self, camera_ids: List[int]) -> None:
        selected = {int(item) for item in camera_ids if int(item) > 0}
        for row in range(self.camera_select.count()):
            item = self.camera_select.item(row)
            item.setSelected(int(item.data(Qt.ItemDataRole.UserRole) or 0) in selected)

    def _selected_camera_ids(self) -> List[int]:
        values: List[int] = []
        for item in self.camera_select.selectedItems():
            camera_id = int(item.data(Qt.ItemDataRole.UserRole) or 0)
            if camera_id > 0:
                values.append(camera_id)
        return values

    def _apply_entry(self, entry: FaceWhitelistEntry) -> None:
        self._selected_image_path = ""
        self.name_edit.setText(entry.name)
        self.face_color_edit.setText(entry.face_color)
        self.hair_color_edit.setText(entry.hair_color)
        self.age_spin.setValue(entry.age or 0)
        self._set_gender_value(entry.gender if entry.gender in {"Male", "Female"} else None)
        self.match_spin.setValue(entry.similarity)
        self._set_selected_camera_ids(entry.camera_ids)
        self.note_edit.setPlainText(entry.note)
        self.choose_image_btn.setEnabled(False)
        self.clear_image_btn.setEnabled(False)
        self.preview_label.setText("Editing details only")

    def _pick_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Face Image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._set_image(path)

    def _set_image(self, image_path: str) -> None:
        self._selected_image_path = image_path
        pix = QPixmap(image_path)
        if pix.isNull():
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText(os.path.basename(image_path))
            return
        self.preview_label.setPixmap(
            pix.scaled(
                self.preview_label.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.preview_label.setText("")

    def _clear_image(self) -> None:
        self._selected_image_path = ""
        self.preview_label.setPixmap(QPixmap())
        self.preview_label.setText("Choose a primary face image")

    def _reset_to_initial_state(self) -> None:
        if self._entry is not None:
            self._apply_entry(self._entry)
            return
        self.name_edit.setText(self._initial_payload.name)
        self.face_color_edit.setText(self._initial_payload.face_color)
        self.hair_color_edit.setText(self._initial_payload.hair_color)
        self.age_spin.setValue(self._initial_payload.age or 0)
        self._set_gender_value(self._initial_payload.gender or None)
        self.match_spin.setValue(self._initial_payload.match)
        self._set_selected_camera_ids(self._initial_payload.camera_ids)
        self.note_edit.setPlainText(self._initial_payload.note)
        if self._initial_image_path:
            self._set_image(self._initial_image_path)
        else:
            self._clear_image()

    def payload(self) -> FaceWhitelistPayload:
        age_value = self.age_spin.value()
        return FaceWhitelistPayload(
            name=self.name_edit.text().strip(),
            face_color=self.face_color_edit.text().strip(),
            hair_color=self.hair_color_edit.text().strip(),
            gender=self._gender_value(),
            age=age_value if age_value > 0 else None,
            match=float(self.match_spin.value()),
            camera_ids=self._selected_camera_ids(),
            note=self.note_edit.toPlainText().strip(),
        )

    def selected_image_path(self) -> str:
        return self._selected_image_path

    def is_edit_mode(self) -> bool:
        return self._entry is not None

    def _submit(self) -> None:
        payload = self.payload()
        if not payload.name:
            self.validation_error.emit("Name is required.")
            return
        if not self.is_edit_mode() and not self._selected_image_path:
            self.validation_error.emit("Choose a primary face image first.")
            return
        self.submitted.emit()

class TemplatesDialog(QDialog):
    add_requested = Signal()
    delete_requested = Signal(str)

    def __init__(
        self,
        net: QNetworkAccessManager,
        auth_token: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._net = net
        self._auth_token = auth_token.strip()
        self._entry: Optional[FaceWhitelistEntry] = None
        self._templates: List[FaceWhitelistTemplate] = []
        self._can_manage = False
        self.setWindowTitle("Person Templates")
        self.resize(960, 680)
        self.setMinimumSize(760, 560)

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        header = QHBoxLayout()
        header.setSpacing(8)
        root.addLayout(header)

        self.summary_label = QLabel("Person: Unknown | Total images: 0")
        self.summary_label.setObjectName("faceDialogInfo")
        header.addWidget(self.summary_label, 1)

        self.add_btn = QPushButton("Add Image")
        self.add_btn.clicked.connect(lambda: self.add_requested.emit())
        header.addWidget(self.add_btn)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)

        self.content = QWidget()
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(12)
        self.scroll.setWidget(self.content)

        self.empty_label = QLabel("No templates available.")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setObjectName("faceDialogHint")
        root.addWidget(self.empty_label)

        self.setStyleSheet(
            """
            QDialog {
                background: #171b21;
                color: #eef2f8;
            }
            QLabel#faceDialogInfo {
                color: #f8fafc;
                font-size: 14px;
                font-weight: 700;
            }
            QLabel#faceDialogHint {
                color: #93a1b6;
                font-size: 12px;
            }
            QFrame#faceTemplateCard {
                background: #10161d;
                border: 1px solid #293241;
                border-radius: 14px;
            }
            QLabel#faceTemplateDate {
                color: #93a1b6;
                font-size: 11px;
            }
            """
            + _DIALOG_BUTTON_QSS
        )

    def set_auth_token(self, token: str) -> None:
        self._auth_token = str(token or "").strip()

    def set_data(self, entry: FaceWhitelistEntry, templates: List[FaceWhitelistTemplate], can_manage: bool) -> None:
        self._entry = entry
        self._templates = list(templates)
        self._can_manage = can_manage
        self.summary_label.setText(
            f"Person: {entry.name or 'Unknown'} | Total images: {len(templates)}"
        )
        self.add_btn.setEnabled(can_manage)
        self._rebuild_grid()

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if self._templates:
            self._rebuild_grid()

    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _column_count(self) -> int:
        viewport = self.scroll.viewport()
        width = viewport.width() if viewport is not None else self.width()
        usable_width = max(320, width - 8)
        target_card_width = 230
        return max(1, usable_width // target_card_width)

    def _rebuild_grid(self) -> None:
        self._clear_grid()

        if not self._templates:
            self.empty_label.show()
            self.content.hide()
            return

        self.empty_label.hide()
        self.content.show()
        columns = self._column_count()

        for index, template in enumerate(self._templates):
            card = QFrame()
            card.setObjectName("faceTemplateCard")
            card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            card.setMinimumWidth(0)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(10, 10, 10, 10)
            card_layout.setSpacing(8)

            top = QHBoxLayout()
            top.setSpacing(6)
            card_layout.addLayout(top)

            top.addStretch(1)
            delete_btn = QToolButton()
            delete_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            delete_btn.setText("×")
            delete_btn.setToolTip("Delete image")
            delete_btn.setEnabled(self._can_manage)
            delete_btn.clicked.connect(lambda _checked=False, tid=template.template_id: self.delete_requested.emit(tid))
            top.addWidget(delete_btn)

            image = RemoteImageLabel(self._net, fallback_text="No Image", auth_token=self._auth_token)
            image.setMinimumHeight(170)
            image.setMaximumHeight(170)
            image.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            image.set_image_url(template.image_url)
            image.setStyleSheet("border-radius: 12px; background: #0c1117;")
            card_layout.addWidget(image)

            created = QLabel(template.created_text or "Unknown date")
            created.setObjectName("faceTemplateDate")
            created.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(created)
            card_layout.addStretch(1)

            row = index // columns
            col = index % columns
            self.grid.addWidget(card, row, col)

        for column in range(columns):
            self.grid.setColumnStretch(column, 1)


class FaceRegistryPage(QWidget):
    navigate = Signal(str)
    current_path = "/face/whitelist"
    toast_title = "Face Whitelist"
    registry_title_text = "Face Whitelist Registry"
    registry_hint_text = "Manage approved face identities, review image templates, and map them to cameras."
    form_title_text = "Face Whitelist"
    form_create_hint_text = "Create a whitelist person and assign one or more cameras."
    form_edit_hint_text = "Update whitelist person details. Use the image actions in the table to manage templates."
    manage_permission = "view_face_whitelist"
    manage_error_text = "You don't have permission to manage the face whitelist."
    service_cls: Type[FaceWhitelistService] = FaceWhitelistService
    store_cls: Type[FaceWhitelistStore] = FaceWhitelistStore

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.toast = PrimeToastHost(self)
        self.net = QNetworkAccessManager(self)
        self._person_form: Optional[PersonFormDialog] = None
        self._person_form_entry: Optional[FaceWhitelistEntry] = None

        self.service = self.service_cls()
        self.auth_store = AuthStore(AuthService())
        self.camera_source_store = CameraDepartmentStore(CameraService())
        self.whitelist_store = self.store_cls(self.service)

        self.auth_store.changed.connect(self.refresh)
        self.auth_store.error.connect(self._show_error)
        self.camera_source_store.changed.connect(self.refresh)
        self.camera_source_store.error.connect(self._show_error)
        self.whitelist_store.changed.connect(self.refresh)
        self.whitelist_store.error.connect(self._show_error)
        self.whitelist_store.success.connect(self._show_success)

        self._build_ui()
        self._apply_style()

        self.auth_store.load()
        self.camera_source_store.get_camera_for_user(None, silent=True)
        self.whitelist_store.load()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(10)

        self.sidebar = WatchlistSidebar(self.current_path, self)
        self.sidebar.navigate.connect(self.navigate.emit)
        root.addWidget(self.sidebar)

        shell = QFrame()
        shell.setObjectName("faceWhiteShell")
        root.addWidget(shell, 1)

        shell_layout = QHBoxLayout(shell)
        shell_layout.setContentsMargins(12, 12, 12, 12)
        shell_layout.setSpacing(12)

        content = QFrame()
        content.setObjectName("faceMainPanel")
        shell_layout.addWidget(content, 1)

        content_stack = QStackedLayout(content)
        content_stack.setContentsMargins(0, 0, 0, 0)
        content_stack.setStackingMode(QStackedLayout.StackingMode.StackAll)

        body = QWidget()
        content_stack.addWidget(body)

        content_layout = QVBoxLayout(body)
        content_layout.setContentsMargins(18, 18, 18, 18)
        content_layout.setSpacing(14)

        hero = QHBoxLayout()
        hero.setSpacing(10)
        content_layout.addLayout(hero)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(4)
        hero.addLayout(hero_text, 1)

        page_title = QLabel(self.registry_title_text)
        page_title.setObjectName("facePageTitle")
        hero_text.addWidget(page_title)

        page_hint = QLabel(self.registry_hint_text)
        page_hint.setObjectName("facePageHint")
        page_hint.setWordWrap(True)
        hero_text.addWidget(page_hint)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        content_layout.addLayout(toolbar)

        self.new_btn = PrimeButton("New Person", variant="primary", size="sm")
        self.new_btn.clicked.connect(self._prepare_create_mode)
        toolbar.addWidget(self.new_btn)

        self.reload_btn = PrimeButton("Reload", variant="secondary", size="sm")
        self.reload_btn.clicked.connect(lambda: self.whitelist_store.load())
        toolbar.addWidget(self.reload_btn)

        toolbar.addStretch(1)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("faceSearchInput")
        self.search_edit.setPlaceholderText("Search by name, gender, color, note, or camera...")
        self.search_edit.setMaximumWidth(360)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        self.table = PrimeDataTable(page_size=10, row_height=96, show_footer=True)
        self.table.set_columns(
            [
                PrimeTableColumn("image", "Primary Image", width=108, sortable=False, searchable=False),
                PrimeTableColumn("name", "Name", width=170),
                PrimeTableColumn("image_count", "Images", width=82),
                PrimeTableColumn("preview", "Preview", width=146, sortable=False, searchable=False),
                PrimeTableColumn("match", "Match (%)", width=96),
                PrimeTableColumn("gender", "Gender", width=86),
                PrimeTableColumn("age", "Age", width=72),
                PrimeTableColumn("face_color", "Face Color", width=110),
                PrimeTableColumn("hair_color", "Hair Color", width=110),
                PrimeTableColumn("cameras", "Cameras", width=230),
                PrimeTableColumn("note", "Notes", stretch=True),
                PrimeTableColumn("actions", "Actions", width=176, sortable=False, searchable=False),
            ]
        )
        self.table.set_cell_widget_factory("image", self._primary_image_cell)
        self.table.set_cell_widget_factory("preview", self._preview_cell)
        self.table.set_cell_widget_factory("match", self._match_cell)
        self.table.set_cell_widget_factory("actions", self._actions_cell)
        content_layout.addWidget(self.table, 1)

        self.form_overlay = QFrame()
        self.form_overlay.setObjectName("faceFormOverlay")
        self.form_overlay.hide()
        content_stack.addWidget(self.form_overlay)

        overlay_layout = QVBoxLayout(self.form_overlay)
        overlay_layout.setContentsMargins(28, 28, 28, 28)
        overlay_layout.setSpacing(0)
        overlay_layout.addStretch(1)

        self.form_host = QWidget()
        self.form_host.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.form_host_layout = QHBoxLayout(self.form_host)
        self.form_host_layout.setContentsMargins(0, 0, 0, 0)
        self.form_host_layout.setSpacing(0)
        self.form_host_layout.addStretch(1)
        self.form_host_layout.addStretch(1)
        overlay_layout.addWidget(self.form_host)

        overlay_layout.addStretch(1)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            WATCHLIST_SIDEBAR_STYLES
            + """
            QWidget {
                color: #eef2f8;
            }
            QFrame#faceWhiteShell {
                background: #1f2024;
                border: 1px solid #2e3138;
                border-radius: 12px;
            }
            QFrame#faceEditorPanel {
                background: #131920;
                border: 1px solid #263141;
                border-radius: 16px;
            }
            QToolButton#faceEditorToggle {
                background: #1a2430;
                border: 1px solid #35507f;
                border-radius: 14px;
                color: #dbeafe;
                font-size: 16px;
                font-weight: 700;
                min-width: 28px;
                max-width: 28px;
                min-height: 84px;
                max-height: 84px;
            }
            QToolButton#faceEditorToggle:hover {
                background: #243448;
            }
            QFrame#faceMainPanel {
                background: #171b21;
                border: 1px solid #2b3340;
                border-radius: 16px;
            }
            QFrame#faceFormOverlay {
                background: rgba(8, 11, 15, 0.76);
                border-radius: 16px;
            }
            QLabel#faceEditorTitle,
            QLabel#facePageTitle {
                color: #f8fafc;
                font-size: 22px;
                font-weight: 700;
            }
            QLabel#faceEditorHint,
            QLabel#facePageHint {
                color: #93a1b6;
                font-size: 13px;
            }
            QLabel#faceEditorMinor {
                background: rgba(59, 130, 246, 0.12);
                border: 1px solid rgba(96, 165, 250, 0.22);
                border-radius: 12px;
                color: #bfdbfe;
                padding: 10px 12px;
                font-size: 12px;
            }
            QLabel#faceFieldLabel {
                color: #d8e1ee;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#faceUploadPreview {
                background: #0f141a;
                border: 1px dashed #38506d;
                border-radius: 16px;
                color: #93a1b6;
                font-size: 13px;
            }
            QLineEdit#faceTextInput,
            QTextEdit,
            QSpinBox,
            QDoubleSpinBox {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 8px 12px;
                min-height: 24px;
            }
            QLineEdit#faceTextInput:focus,
            QTextEdit:focus,
            QSpinBox:focus,
            QDoubleSpinBox:focus {
                border-color: #4e7cff;
            }
            QLineEdit#faceSearchInput {
                background: #242a33;
                border: 1px solid #364150;
                border-radius: 10px;
                color: #eef2f8;
                padding: 9px 12px;
                min-height: 24px;
            }
            QLabel#faceChip {
                padding: 5px 10px;
                border-radius: 12px;
                background: rgba(59, 130, 246, 0.16);
                border: 1px solid rgba(96, 165, 250, 0.32);
                color: #dbeafe;
                font-size: 11px;
                font-weight: 700;
            }
            QLabel#faceMultiPreviewCount {
                color: #93a1b6;
                font-size: 11px;
                font-weight: 700;
            }
            """
        )

    def showEvent(self, event) -> None:  # type: ignore[override]
        self.camera_source_store.get_camera_for_user(None, silent=True)
        self.whitelist_store.load()
        super().showEvent(event)

    def _auth_token(self) -> str:
        return self.service.api._auth_token()

    def _camera_options(self) -> List[dict]:
        options: List[dict] = []
        for camera in self.camera_source_store.cameras:
            label = camera.name or f"Camera #{camera.id}"
            if camera.camera_ip:
                label = f"{label} ({camera.camera_ip})"
            options.append({"label": label, "value": camera.id})
        return options

    def _can_manage(self) -> bool:
        if self.auth_store.current_user is None:
            return False
        return self.auth_store.has_permission(self.manage_permission)

    def refresh(self) -> None:
        self.new_btn.setEnabled(self._can_manage())
        self.table.set_rows(self._rows())
        self.table.set_filter_text(self.search_edit.text())

    def _rows(self) -> List[Dict[str, object]]:
        rows: List[Dict[str, object]] = []
        for entry in self.whitelist_store.entries:
            rows.append(
                {
                    "image": entry.image_url,
                    "name": entry.name or "Unknown",
                    "image_count": str(entry.image_count),
                    "preview": str(entry.image_count),
                    "match": entry.similarity_text,
                    "gender": entry.gender or "Unset",
                    "age": str(entry.age) if entry.age is not None else "Unset",
                    "face_color": entry.face_color or "Unset",
                    "hair_color": entry.hair_color or "Unset",
                    "cameras": entry.cameras_text,
                    "note": entry.note or "",
                    "_entry": entry,
                }
            )
        return rows

    def _on_search_changed(self, text: str) -> None:
        self.table.set_filter_text(text)

    def _prepare_create_mode(self) -> None:
        self._open_person_dialog()

    def _populate_form(self, entry: FaceWhitelistEntry) -> None:
        self._open_person_dialog(entry=entry)

    def _open_person_dialog(
        self,
        entry: Optional[FaceWhitelistEntry] = None,
        *,
        prefill_name: str = "",
        prefill_image_path: str = "",
    ) -> None:
        if not self._can_manage():
            self._show_error(self.manage_error_text)
            return

        if self._person_form is None:
            self._person_form = PersonFormDialog(
                camera_options=self._camera_options(),
                entry=entry,
                prefill_name=prefill_name,
                prefill_image_path=prefill_image_path,
                title_text=self.form_title_text,
                create_hint_text=self.form_create_hint_text,
                edit_hint_text=self.form_edit_hint_text,
                parent=self.form_overlay,
            )
            self._person_form.validation_error.connect(self._show_error)
            self._person_form.cancelled.connect(self._close_person_form)
            self._person_form.submitted.connect(self._submit_person_form)
            self.form_host_layout.insertWidget(1, self._person_form, 0, Qt.AlignmentFlag.AlignCenter)
        else:
            self._person_form.configure(
                camera_options=self._camera_options(),
                entry=entry,
                prefill_name=prefill_name,
                prefill_image_path=prefill_image_path,
                title_text=self.form_title_text,
                create_hint_text=self.form_create_hint_text,
                edit_hint_text=self.form_edit_hint_text,
            )
        self._person_form_entry = entry
        self.form_overlay.show()
        self.form_overlay.raise_()
        self._person_form.show()

    def _close_person_form(self) -> None:
        self._person_form_entry = None
        if self._person_form is not None:
            self._person_form.hide()
        self.form_overlay.hide()

    def _submit_person_form(self) -> None:
        dialog = self._person_form
        entry = self._person_form_entry
        if dialog is None:
            return

        payload = dialog.payload()
        image_path = dialog.selected_image_path()
        self._close_person_form()

        if entry is not None:
            self.whitelist_store.update_entry(entry.identifier, payload)
            return

        try:
            message, person_id = self.service.create_entry(payload, image_path=image_path)
            self.whitelist_store.load()
            self.toast.success(self.toast_title, message)
            created_entry = self.whitelist_store.find_entry(person_id) if person_id else None
            created_entry = created_entry or (self.whitelist_store.entries[-1] if self.whitelist_store.entries else None)
            if created_entry is not None:
                self._open_add_image_dialog(created_entry)
        except Exception as exc:
            self._show_error(str(exc))

    def _action_button(
        self,
        *,
        icon_name: str = "",
        text: str = "",
        bg: str,
        border: str,
    ) -> QToolButton:
        btn = QToolButton()
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setFixedSize(32, 32)
        btn.setText(text)
        btn.setStyleSheet(
            f"""
            QToolButton {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 16px;
                color: #f8fafc;
                font-size: 13px;
                font-weight: 700;
            }}
            QToolButton:hover {{
                border-color: #f8fafc;
            }}
            """
        )
        if icon_name:
            icon_file = _icon_path(icon_name)
            if os.path.isfile(icon_file):
                btn.setIcon(QIcon(icon_file))
                btn.setIconSize(QSize(16, 16))
        return btn

    def _primary_image_cell(self, row: Dict[str, object]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        image = RemoteImageLabel(self.net, fallback_text="No Image", auth_token=self._auth_token())
        image.setFixedSize(72, 72)
        image.setStyleSheet("border-radius: 12px; background: #0e141b;")
        image.set_image_url(str(row.get("image") or ""))
        layout.addWidget(image, 0, Qt.AlignmentFlag.AlignCenter)
        layout.addStretch(1)
        return wrapper

    def _preview_cell(self, row: Dict[str, object]) -> QWidget:
        entry = row.get("_entry")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        if not isinstance(entry, FaceWhitelistEntry):
            return wrapper

        previews = entry.preview_images[:3]
        for image_url in previews:
            image = RemoteImageLabel(self.net, fallback_text="", auth_token=self._auth_token())
            image.setFixedSize(28, 28)
            image.setStyleSheet("border-radius: 14px; background: #0e141b; border: 1px solid #293241;")
            image.set_image_url(image_url)
            layout.addWidget(image)

        extra = max(0, entry.image_count - len(previews))
        if extra > 0:
            extra_label = QLabel(f"+{extra}")
            extra_label.setObjectName("faceMultiPreviewCount")
            layout.addWidget(extra_label)

        layout.addStretch(1)
        return wrapper

    def _match_cell(self, row: Dict[str, object]) -> QWidget:
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        chip = QLabel(str(row.get("match") or "0.00%"))
        chip.setObjectName("faceChip")
        layout.addWidget(chip, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        layout.addStretch(1)
        return wrapper

    def _actions_cell(self, row: Dict[str, object]) -> QWidget:
        entry = row.get("_entry")
        wrapper = QWidget()
        layout = QHBoxLayout(wrapper)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        if not isinstance(entry, FaceWhitelistEntry):
            return wrapper

        can_manage = self._can_manage()

        templates_btn = self._action_button(icon_name="view.svg", bg="#20344f", border="#35507f")
        templates_btn.setToolTip("View templates")
        templates_btn.clicked.connect(lambda: self._open_templates(entry))
        layout.addWidget(templates_btn)

        add_btn = self._action_button(text="+", bg="#173328", border="#1f7a4f")
        add_btn.setToolTip("Add image")
        add_btn.setEnabled(can_manage)
        add_btn.clicked.connect(lambda: self._open_add_image_dialog(entry))
        layout.addWidget(add_btn)

        edit_btn = self._action_button(icon_name="edit.svg", bg="#35507f", border="#4d76bb")
        edit_btn.setToolTip("Edit details")
        edit_btn.setEnabled(can_manage)
        edit_btn.clicked.connect(lambda: self._populate_form(entry))
        layout.addWidget(edit_btn)

        delete_btn = self._action_button(icon_name="trash.svg", bg="#8b2f3f", border="#bb4d62")
        delete_btn.setToolTip("Delete person")
        delete_btn.setEnabled(can_manage)
        delete_btn.clicked.connect(lambda: self._confirm_delete_person(entry))
        layout.addWidget(delete_btn)
        return wrapper

    def _open_templates(self, entry: FaceWhitelistEntry) -> None:
        dialog = TemplatesDialog(self.net, auth_token=self._auth_token(), parent=self)

        def refresh_dialog() -> FaceWhitelistEntry:
            refreshed = self.whitelist_store.find_entry(entry.identifier) or entry
            templates = self.whitelist_store.load_templates(refreshed.identifier)
            dialog.set_data(refreshed, templates, self._can_manage())
            return refreshed

        def handle_add() -> None:
            current_entry = self.whitelist_store.find_entry(entry.identifier) or entry
            self._open_add_image_dialog(current_entry, parent=dialog)
            refresh_dialog()

        def handle_delete(template_id: str) -> None:
            current_entry = self.whitelist_store.find_entry(entry.identifier) or entry
            result = QMessageBox.question(
                dialog,
                "Delete Image",
                "Delete this template image?",
            )
            if result != QMessageBox.StandardButton.Yes:
                return
            success = self.whitelist_store.delete_template_image(current_entry.identifier, template_id)
            if success:
                refresh_dialog()

        dialog.add_requested.connect(handle_add)
        dialog.delete_requested.connect(handle_delete)
        refresh_dialog()
        dialog.exec()

    def _open_add_image_dialog(
        self,
        entry: FaceWhitelistEntry,
        parent: Optional[QWidget] = None,
    ) -> None:
        dialog = AddImageDialog(parent or self)
        templates = self.whitelist_store.load_templates(entry.identifier)
        dialog.set_person(entry, len(templates))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        image_path = dialog.selected_image_path()
        try:
            message = self.service.add_image(entry.identifier, image_path)
            self.whitelist_store.load()
            self.whitelist_store.load_templates(entry.identifier)
            self.toast.success(self.toast_title, message)
        except LowSimilarityError as exc:
            warning = LowSimilarityDialog(parent or self)
            warning.set_error(exc)
            result = warning.exec()
            if result == QDialog.DialogCode.Accepted:
                self._open_person_dialog(
                    prefill_name=entry.name,
                    prefill_image_path=image_path,
                )
        except Exception as exc:
            self._show_error(str(exc))

    def _confirm_delete_person(self, entry: FaceWhitelistEntry) -> None:
        result = QMessageBox.question(
            self,
            "Delete Person",
            f"Delete '{entry.name or entry.identifier}' and all template images?",
        )
        if result == QMessageBox.StandardButton.Yes:
            self.whitelist_store.delete_entry(entry.identifier)

    def _show_success(self, text: str) -> None:
        self.toast.success(self.toast_title, text)

    def _show_error(self, text: str) -> None:
        self.toast.error(self.toast_title, text)


class WhitelistPage(FaceRegistryPage):
    pass
