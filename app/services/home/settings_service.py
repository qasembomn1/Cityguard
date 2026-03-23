from __future__ import annotations

import os
from typing import Any, Dict, Iterable, Tuple

from app.api.api_service import ApiService
from app.models.settings import AlarmSetting, RecordSetting, RepeatedSetting


class SettingsService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _should_retry_fallback(self, exc: Exception) -> bool:
        message = str(exc)
        return "[404]" in message or "[405]" in message

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Dict[str, Any] | None = None,
    ) -> Any:
        attempts_list = list(attempts)
        last_exc: Exception | None = None
        for index, (method, path) in enumerate(attempts_list):
            try:
                return self.api.request(method, path, data=data, auth=True)
            except Exception as exc:
                last_exc = exc
                is_last_attempt = index == len(attempts_list) - 1
                if is_last_attempt or not self._should_retry_fallback(exc):
                    break
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No settings API attempts configured.")

    def _extract_object(self, payload: Any, keys: tuple[str, ...]) -> Dict[str, Any]:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if isinstance(value, dict):
                    return value
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    resolved = self._extract_object(nested, keys)
                    if resolved:
                        return resolved
            return payload
        return {}

    def _extract_message(self, payload: Any, default: str) -> str:
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("detail") or payload.get("result") or "").strip()
            if message:
                return message
        return default

    def _extract_data(self, payload: Any) -> Any:
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                if nested not in (None, "", [], {}):
                    return self._extract_data(nested)
            return payload
        return payload

    def get_alarm_setting(self) -> AlarmSetting:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/settings/alarm_setting/"),
                ("GET", "/api/v1/settings/alarm_setting"),
            )
        )
        return AlarmSetting.from_dict(self._extract_object(payload, ("alarm_setting", "alarm")))

    def update_alarm_setting(
        self,
        payload: Dict[str, Any] | AlarmSetting,
    ) -> Tuple[AlarmSetting, str]:
        data = payload.to_dict() if isinstance(payload, AlarmSetting) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", "/api/v1/settings/alarm_setting/update"),
                ("PATCH", "/api/v1/settings/alarm_setting/update/"),
            ),
            data=data,
        )
        return (
            self.get_alarm_setting(),
            self._extract_message(response, "Alarm settings updated successfully."),
        )

    def get_repeated_setting(self) -> RepeatedSetting:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/settings/repeated_setting/"),
                ("GET", "/api/v1/settings/repeated_setting"),
            )
        )
        return RepeatedSetting.from_dict(self._extract_object(payload, ("repeated_setting", "repeated")))

    def update_repeated_setting(
        self,
        payload: Dict[str, Any] | RepeatedSetting,
    ) -> Tuple[RepeatedSetting, str]:
        data = payload.to_dict() if isinstance(payload, RepeatedSetting) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", "/api/v1/settings/repeated_setting/update"),
                ("PATCH", "/api/v1/settings/repeated_setting/update/"),
            ),
            data=data,
        )
        return (
            self.get_repeated_setting(),
            self._extract_message(response, "Repeated settings updated successfully."),
        )

    def get_record_setting(self) -> RecordSetting:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/settings/record_setting/"),
                ("GET", "/api/v1/settings/record_setting"),
            )
        )
        return RecordSetting.from_dict(self._extract_object(payload, ("record_setting", "record")))

    def update_record_setting(
        self,
        payload: Dict[str, Any] | RecordSetting,
    ) -> Tuple[RecordSetting, str]:
        data = payload.to_dict() if isinstance(payload, RecordSetting) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("PATCH", "/api/v1/settings/record_setting/update"),
                ("PATCH", "/api/v1/settings/record_setting/update/"),
            ),
            data=data,
        )
        return (
            self.get_record_setting(),
            self._extract_message(response, "Record settings updated successfully."),
        )

    def get_network_interfaces(self) -> Any:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/server_settings/network/interfaces"),
                ("GET", "/api/v1/server_settings/network/interfaces/"),
            )
        )
        return self._extract_data(payload)

    def get_network_ips(self) -> Any:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/server_settings/network/ips"),
                ("GET", "/api/v1/server_settings/network/ips/"),
            )
        )
        return self._extract_data(payload)

    def set_static_ip(self, payload: Dict[str, Any]) -> str:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/server_settings/network/set-static-ip"),
                ("POST", "/api/v1/server_settings/network/set-static-ip/"),
            ),
            data=dict(payload or {}),
        )
        return self._extract_message(response, "Static IP updated successfully.")

    def add_network_ip(self, payload: Dict[str, Any]) -> str:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/server_settings/network/add-ip"),
                ("POST", "/api/v1/server_settings/network/add-ip/"),
            ),
            data=dict(payload or {}),
        )
        return self._extract_message(response, "IP address added successfully.")

    def remove_network_ip(self, payload: Dict[str, Any]) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", "/api/v1/server_settings/network/remove-ip"),
                ("DELETE", "/api/v1/server_settings/network/remove-ip/"),
            ),
            data=dict(payload or {}),
        )
        return self._extract_message(response, "IP address removed successfully.")

    def reboot_system(self) -> str:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/server_settings/system/reboot"),
                ("POST", "/api/v1/server_settings/system/reboot/"),
            )
        )
        return self._extract_message(response, "Reboot requested successfully.")

    def shutdown_system(self) -> str:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/server_settings/system/shutdown"),
                ("POST", "/api/v1/server_settings/system/shutdown/"),
            )
        )
        return self._extract_message(response, "Shutdown requested successfully.")

    def cancel_shutdown(self) -> str:
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/server_settings/system/cancel-shutdown"),
                ("POST", "/api/v1/server_settings/system/cancel-shutdown/"),
            )
        )
        return self._extract_message(response, "Shutdown cancellation requested successfully.")
