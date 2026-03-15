import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from app.api.api_service import ApiService
from app.models.client import Client
from app.models.user import User
from app.models.auth import ActivationInfo


class AuthService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def login(self, user: Dict[str, Any]) -> Dict[str, Any]:
        credentials = dict(user or {})
        if not credentials.get("username") or not credentials.get("password"):
            raise ValueError("Username and password are required.")

        try:
            payload = self.api.post("/api/v1/auth/login", credentials)
        except RuntimeError as exc:
            if "[404]" not in str(exc):
                raise
            payload = self.api.post("/api/v1/auth/login/", credentials)

        return payload if isinstance(payload, dict) else {}

    def get_current_user(self) -> User:
        try:
            profile = self.api.get("/api/v1/auth/profile/", auth=True)
        except Exception:
            return User()

        if not isinstance(profile, dict):
            return User()

        raw_permissions = profile.get("permissions") or []
        permissions: List[str] = []
        if isinstance(raw_permissions, list):
            for item in raw_permissions:
                if isinstance(item, str):
                    permissions.append(item)
                elif isinstance(item, dict):
                    for key in ("name", "permission", "code", "slug"):
                        value = item.get(key)
                        if isinstance(value, str) and value:
                            permissions.append(value)
                            break

        return User(
            id=int(profile.get("id") or 0),
            name=str(profile.get("name") or profile.get("username") or "User"),
            department_id=profile.get("department_id"),
            is_superadmin=bool(profile.get("is_superadmin") or profile.get("is_super_admin")),
            permissions=permissions,
        )

    def _auth_headers(self, auth: bool = False) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        if auth:
            token = self.api._auth_token()
            if token:
                headers["Authorization"] = f"Bearer {token}"
        return headers

    def _parse_datetime_text(self, value: Any) -> Optional[datetime]:
        text = str(value or "").strip()
        if not text:
            return None
        normalized = text.replace("Z", "+00:00")
        for candidate in (
            normalized,
            normalized.replace("T", " "),
        ):
            try:
                return datetime.fromisoformat(candidate)
            except ValueError:
                continue
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%d/%m/%Y %H:%M:%S",
            "%d/%m/%Y %H:%M",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
        ):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    def _as_int(self, value: Any, default: int = -1) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def _parse_activation_info(self, payload: Any) -> ActivationInfo:
        if not isinstance(payload, dict):
            return ActivationInfo(camera_limit=-1)

        expire_date = str(
            payload.get("expire_date")
            or payload.get("expires_at")
            or payload.get("expiry_date")
            or ""
        ).strip()
        expires_at = self._parse_datetime_text(expire_date)
        activated = bool(payload.get("activated") or payload.get("is_active"))
        if not activated and expires_at is not None:
            now = datetime.now(expires_at.tzinfo) if expires_at.tzinfo else datetime.now()
            activated = expires_at > now

        return ActivationInfo(
            camera_limit=self._as_int(payload.get("camera_limit"), -1),
            device_id=str(payload.get("device_id") or payload.get("device") or "").strip(),
            server_address=str(
                payload.get("server_adress")
                or payload.get("server_address")
                or payload.get("server_ip")
                or ""
            ).strip(),
            expire_date=expire_date,
            activated=activated,
        )

    def _client_base_url(self, client: Client) -> str:
        ip = str(getattr(client, "ip", "") or "").strip()
        port = int(getattr(client, "port", 0) or 0)
        if not ip:
            raise RuntimeError("Client IP is missing.")
        return f"http://{ip}:{port}" if port > 0 else f"http://{ip}"

    def _request_json(self, method: str, url: str, auth: bool = False) -> Any:
        try:
            response = self.api.client.request(
                method.upper(),
                url,
                headers=self._auth_headers(auth=auth),
                timeout=self.api.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = (exc.response.text or "").strip()
            raise RuntimeError(
                f"API request failed [{exc.response.status_code}] {method.upper()} {url}. {detail}".strip()
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach API at {url}: {exc}") from exc

        payload = response.text.strip()
        if not payload:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"message": payload}

    def _post_file(self, url: str, field_name: str, file_path: str, auth: bool = False) -> Any:
        try:
            with open(file_path, "rb") as handle:
                response = self.api.client.post(
                    url,
                    files={field_name: (os.path.basename(file_path), handle, "application/octet-stream")},
                    headers=self._auth_headers(auth=auth),
                    timeout=self.api.timeout,
                )
                response.raise_for_status()
        except FileNotFoundError as exc:
            raise RuntimeError(f"File not found: {file_path}") from exc
        except httpx.HTTPStatusError as exc:
            detail = (exc.response.text or "").strip()
            raise RuntimeError(
                f"API request failed [{exc.response.status_code}] POST {url}. {detail}".strip()
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach API at {url}: {exc}") from exc

        payload = response.text.strip()
        if not payload:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"message": payload}

    def get_activation_info(self, client: Client | None = None) -> ActivationInfo:
        if client is not None:
            url = f"{self._client_base_url(client)}/get_activate_info"
            return self._parse_activation_info(self._request_json("GET", url, auth=False))

        try:
            data = self.api.get("/api/v1/auth/get_activate_info", auth=True)
            if isinstance(data, dict):
                return self._parse_activation_info(data)
        except Exception:
            pass
        return ActivationInfo(camera_limit=-1)

    def activate_client(self, client: Client, key_file_path: str) -> ActivationInfo:
        url = f"{self._client_base_url(client)}/import_key"
        self._post_file(url, "key_file", key_file_path, auth=False)
        return self.get_activation_info(client)

    def activate_server(self, key_file_path: str) -> ActivationInfo:
        server_url = f"{self.api.base_url.rstrip('/')}/api/v1/auth/import_key"
        self._post_file(server_url, "key_file", key_file_path, auth=True)
        return self.get_activation_info()
