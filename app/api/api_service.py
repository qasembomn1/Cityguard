from __future__ import annotations

import json
import os
import urllib.parse
from typing import Any, Dict, Optional

import httpx


class ApiService:
    def __init__(self, base_url: str | None, timeout: float = 12.0):
        resolved_base_url = (base_url or "http://192.168.100.120:8800").strip().rstrip("/")
        self.base_url = resolved_base_url
        self.timeout = timeout
        self.client = httpx.Client(timeout=self.timeout, follow_redirects=True)

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
        normalized_path = path if path.startswith("/") else f"/{path}"
        url = f"{self.base_url}{normalized_path}"
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

        body = json.dumps(data).encode("utf-8") if data is not None else None
        try:
            response = self.client.request(
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
