from __future__ import annotations

from typing import Any, Optional

from app.models.settings import AlarmSetting, RecordSetting, RepeatedSetting
from app.services.home.settings_service import SettingsService
from app.store._init_ import BaseStore


class SettingsStore(BaseStore):
    def __init__(self, service: SettingsService) -> None:
        super().__init__()
        self.service = service
        self.record_setting = RecordSetting()
        self.alarm_setting = AlarmSetting()
        self.repeated_setting = RepeatedSetting()
        self.network_interfaces: Any = []
        self.network_ips: Any = []
        self.last_error = ""
        self.last_message = ""

    def _clear_feedback(self) -> None:
        self.last_error = ""
        self.last_message = ""

    def _remember_error(self, exc: Exception) -> None:
        self.last_error = str(exc)
        self.emit_error(self.last_error)

    def _remember_success(self, message: str) -> None:
        self.last_message = message
        self.emit_success(message)

    def load_record_setting(self) -> Optional[RecordSetting]:
        self._clear_feedback()
        try:
            self.record_setting = self.service.get_record_setting()
            self.changed.emit()
            return self.record_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def update_record_setting(self, payload: RecordSetting) -> Optional[RecordSetting]:
        self._clear_feedback()
        try:
            self.record_setting, message = self.service.update_record_setting(payload)
            self._remember_success(message)
            return self.record_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def load_alarm_setting(self) -> Optional[AlarmSetting]:
        self._clear_feedback()
        try:
            self.alarm_setting = self.service.get_alarm_setting()
            self.changed.emit()
            return self.alarm_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def update_alarm_setting(self, payload: AlarmSetting) -> Optional[AlarmSetting]:
        self._clear_feedback()
        try:
            self.alarm_setting, message = self.service.update_alarm_setting(payload)
            self._remember_success(message)
            return self.alarm_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def load_repeated_setting(self) -> Optional[RepeatedSetting]:
        self._clear_feedback()
        try:
            self.repeated_setting = self.service.get_repeated_setting()
            self.changed.emit()
            return self.repeated_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def update_repeated_setting(self, payload: RepeatedSetting) -> Optional[RepeatedSetting]:
        self._clear_feedback()
        try:
            self.repeated_setting, message = self.service.update_repeated_setting(payload)
            self._remember_success(message)
            return self.repeated_setting
        except Exception as exc:
            self._remember_error(exc)
            return None

    def load_network_interfaces(self) -> Optional[Any]:
        self._clear_feedback()
        try:
            self.network_interfaces = self.service.get_network_interfaces()
            self.changed.emit()
            return self.network_interfaces
        except Exception as exc:
            self._remember_error(exc)
            return None

    def load_network_ips(self) -> Optional[Any]:
        self._clear_feedback()
        try:
            self.network_ips = self.service.get_network_ips()
            self.changed.emit()
            return self.network_ips
        except Exception as exc:
            self._remember_error(exc)
            return None

    def set_static_ip(self, payload: dict[str, Any]) -> bool:
        self._clear_feedback()
        try:
            message = self.service.set_static_ip(payload)
            self.network_interfaces = self.service.get_network_interfaces()
            self.network_ips = self.service.get_network_ips()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False

    def add_network_ip(self, payload: dict[str, Any]) -> bool:
        self._clear_feedback()
        try:
            message = self.service.add_network_ip(payload)
            self.network_interfaces = self.service.get_network_interfaces()
            self.network_ips = self.service.get_network_ips()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False

    def remove_network_ip(self, payload: dict[str, Any]) -> bool:
        self._clear_feedback()
        try:
            message = self.service.remove_network_ip(payload)
            self.network_interfaces = self.service.get_network_interfaces()
            self.network_ips = self.service.get_network_ips()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False

    def reboot_system(self) -> bool:
        self._clear_feedback()
        try:
            message = self.service.reboot_system()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False

    def shutdown_system(self) -> bool:
        self._clear_feedback()
        try:
            message = self.service.shutdown_system()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False

    def cancel_shutdown(self) -> bool:
        self._clear_feedback()
        try:
            message = self.service.cancel_shutdown()
            self._remember_success(message)
            return True
        except Exception as exc:
            self._remember_error(exc)
            return False
