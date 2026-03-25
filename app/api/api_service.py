from __future__ import annotations

import json
import os
import ssl
import urllib.parse
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from app.utils.env import resolve_http_base_url

_SSL_CONTEXT: ssl.SSLContext | None = None


def _build_ssl_context() -> ssl.SSLContext:
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT

    for env_name in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        candidate = (os.getenv(env_name) or "").strip()
        if candidate and os.path.isfile(candidate):
            _SSL_CONTEXT = ssl.create_default_context(cafile=candidate)
            return _SSL_CONTEXT

    for candidate in (
        "/etc/ssl/certs/ca-certificates.crt",
        "/etc/pki/tls/certs/ca-bundle.crt",
        "/etc/ssl/ca-bundle.pem",
        "/etc/ssl/cert.pem",
    ):
        if os.path.isfile(candidate):
            _SSL_CONTEXT = ssl.create_default_context(cafile=candidate)
            return _SSL_CONTEXT

    _SSL_CONTEXT = ssl.create_default_context()
    return _SSL_CONTEXT


def _json_compatible(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if is_dataclass(value):
        return _json_compatible(asdict(value))
    if isinstance(value, dict):
        return {str(key): _json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_compatible(item) for item in value]
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _json_compatible(to_dict())
    return value


def _resolve_request_url(base_url: str, path: str) -> str:
    raw_path = str(path or "").strip()
    if raw_path.startswith(("http://", "https://")):
        return raw_path

    normalized_path = raw_path if raw_path.startswith("/") else f"/{raw_path}"
    return f"{base_url}{normalized_path}"


class ApiService:
    def __init__(self, base_url: str | None, timeout: float = 12.0):
        resolved_base_url = resolve_http_base_url(base_url)
        self.base_url = resolved_base_url
        self.timeout = timeout
        self._clients: dict[str, httpx.Client] = {}

    @property
    def client(self) -> httpx.Client:
        return self._client_for_url(self.base_url)

    def _client_for_url(self, url: str) -> httpx.Client:
        scheme = (urllib.parse.urlsplit(str(url or self.base_url)).scheme or "http").lower()
        client = self._clients.get(scheme)
        if client is not None:
            return client

        client_kwargs = {
            "timeout": self.timeout,
            "follow_redirects": True,
            "trust_env": False,
        }
        if scheme == "https":
            client_kwargs["verify"] = _build_ssl_context()

        client = httpx.Client(**client_kwargs)
        self._clients[scheme] = client
        return client

    def _auth_token(self) -> str:
        return (
            os.getenv("AUTH_TOKEN")
            or os.getenv("ACCESS_TOKEN")
            or os.getenv("TOKEN")
            or ""
        ).strip()

    def _api_request_json(
        self,
        path: str,
        method: str = "GET",
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        auth: bool = False,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        url = _resolve_request_url(self.base_url, path)
        query = urllib.parse.urlencode(
            {k: v for k, v in (params or {}).items() if v is not None},
            doseq=True,
        )
        if query:
            url = f"{url}?{query}"

        request_headers = {"accept": "application/json"}
        if data is not None:
            request_headers["content-type"] = "application/json"
        if auth:
            token = self._auth_token()
            if token:
                request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)

        try:
            body = json.dumps(_json_compatible(data)).encode("utf-8") if data is not None else None
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Unable to serialize request payload for {method.upper()} {url}: {exc}"
            ) from exc

        try:
            response = self._client_for_url(url).request(
                method=method.upper(),
                url=url,
                content=body,
                headers=request_headers,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.text.strip()
            if not payload:
                return {}
            return response.json()
        except httpx.HTTPStatusError as exc:
            detail = (exc.response.text or "").strip()
            location = (exc.response.headers.get("location") or "").strip()
            redirect_note = f" Redirected to {location}." if location else ""
            raise RuntimeError(
                (
                    f"API request failed [{exc.response.status_code}] {method.upper()} {url}."
                    f"{redirect_note} {detail}"
                ).strip()
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach API at {url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response from {url}.") from exc

    def request(
        self,
        method: str,
        url: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        auth: bool = False,
    ) -> Any:
        return self._api_request_json(
            path=url,
            method=method,
            data=data,
            params=params,
            auth=auth,
            headers=headers,
        )

    def get(self, url: str, params: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        return self.request("GET", url, params=params, auth=auth)

    def post(self, url: str, data: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        return self.request("POST", url, data=data, auth=auth)

    def put(self, url: str, data: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        return self.request("PUT", url, data=data, auth=auth)

    def patch(self, url: str, data: Optional[Dict[str, Any]] = None, auth: bool = False) -> Any:
        return self.request("PATCH", url, data=data, auth=auth)

    def delete(self, url: str, auth: bool = False) -> Any:
        return self.request("DELETE", url, auth=auth)
