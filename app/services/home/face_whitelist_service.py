from __future__ import annotations

import base64
import json
import mimetypes
import os
import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

import httpx

from app.api.api_service import ApiService
from app.models.face.whitelist import FaceWhitelistEntry, FaceWhitelistPayload, FaceWhitelistTemplate
from app.utils.list import extract_dict_list


@dataclass
class LowSimilarityError(RuntimeError):
    person_id: str = ""
    similarity: float = 0.0
    required_similarity: float = 0.0
    message: str = ""

    def __post_init__(self) -> None:
        RuntimeError.__init__(self, self.message or "Image does not match this person.")


class FaceWhitelistService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))

    def _auth_headers(self) -> Dict[str, str]:
        headers = {"accept": "application/json"}
        token = self.api._auth_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str]],
        data: Dict[str, Any] | None = None,
    ) -> Any:
        last_exc: Exception | None = None
        for method, path in attempts:
            try:
                payload = self.api.request(method, path, data=data, auth=True)
                self._raise_if_failed(payload)
                return payload
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No face whitelist API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        keys = ("items", "data", "results", "face_whitelists", "face_whitelist")
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if any(key in payload for key in ("person_id", "name", "image")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _extract_templates(self, payload: Any) -> List[Dict[str, Any]]:
        keys = ("templates", "images", "photos", "data", "results")
        items = extract_dict_list(payload, keys=keys)
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(nested, keys=keys)
                if nested_items:
                    return nested_items
            if any(key in payload for key in ("template_id", "image_url", "filename")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _extract_message(self, payload: Any, default: str) -> str:
        if isinstance(payload, str) and payload.strip():
            return payload.strip()
        if isinstance(payload, dict):
            message = str(payload.get("message") or payload.get("detail") or payload.get("result") or "").strip()
            if message:
                return message
        return default

    def _extract_person_id(self, payload: Any) -> str:
        if isinstance(payload, dict):
            for key in ("person_id", "id"):
                value = payload.get(key)
                if value not in (None, ""):
                    return str(value)
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    person_id = self._extract_person_id(nested)
                    if person_id:
                        return person_id
        return ""

    def _raise_if_failed(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            return
        error_code = str(payload.get("error") or "").strip().lower()
        status = str(payload.get("status") or "").strip().lower()
        if error_code == "low_similarity":
            raise LowSimilarityError(
                person_id=str(payload.get("person_id") or ""),
                similarity=float(payload.get("similarity") or 0.0),
                required_similarity=float(payload.get("required_similarity") or 0.0),
                message=self._extract_message(
                    payload,
                    "New image does not match this person. Try another image or create a new record.",
                ),
            )
        if error_code or status in {"failed", "error"}:
            raise RuntimeError(self._extract_message(payload, "Face whitelist request failed."))

    def _full_url(self, path: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.api.base_url}{normalized_path}"

    def _resolve_image_url(self, value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        lowered = text.lower()
        if lowered.startswith(("http://", "https://", "data:image/")):
            return text
        if text.startswith("/"):
            return f"{self.api.base_url}{text}"
        if text.startswith("api/"):
            return f"{self.api.base_url}/{text}"
        encoded = urllib.parse.quote(text)
        return f"{self.api.base_url}/api/v1/face_whitelists/image/{encoded}"

    def _normalize_entry(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(raw)
        previews: List[str] = []
        for key in ("preview_images", "photos", "images", "templates"):
            values = normalized.get(key)
            if not isinstance(values, list):
                continue
            for item in values:
                if isinstance(item, dict):
                    candidate = (
                        item.get("image_url")
                        or item.get("image")
                        or item.get("url")
                        or item.get("file")
                        or item.get("filename")
                    )
                else:
                    candidate = item
                image_url = self._resolve_image_url(candidate)
                if image_url:
                    previews.append(image_url)
            if previews:
                break
        normalized["preview_images"] = previews

        primary = (
            normalized.get("image")
            or normalized.get("image_url")
            or normalized.get("face")
            or normalized.get("photo")
        )
        normalized["image"] = self._resolve_image_url(primary or (previews[0] if previews else ""))
        return normalized

    def _normalize_template(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(raw)
        normalized["image_url"] = self._resolve_image_url(
            normalized.get("image_url")
            or normalized.get("image")
            or normalized.get("url")
            or normalized.get("file")
            or normalized.get("filename")
        )
        return normalized

    def _stringify_form_fields(self, payload: Dict[str, Any]) -> Dict[str, str]:
        fields: Dict[str, str] = {}
        for key, value in payload.items():
            if value in (None, "", []):
                continue
            if isinstance(value, bool):
                fields[key] = "true" if value else "false"
            elif isinstance(value, (int, float)):
                fields[key] = str(value)
            elif isinstance(value, (list, dict)):
                fields[key] = json.dumps(value)
            else:
                fields[key] = str(value)
        return fields

    def _image_json_fields(self, image_path: str) -> Dict[str, str]:
        mime = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        data_url = f"data:{mime};base64,{encoded}"
        return {
            "face": data_url,
            "crop_face": data_url,
        }

    def _extract_nested_value(self, payload: Any, keys: Sequence[str]) -> Any:
        if isinstance(payload, dict):
            for key in keys:
                value = payload.get(key)
                if value not in (None, "", [], {}):
                    return value
            for nested_key in ("data", "result", "payload"):
                nested_value = self._extract_nested_value(payload.get(nested_key), keys)
                if nested_value not in (None, "", [], {}):
                    return nested_value
        elif isinstance(payload, list):
            for item in payload:
                nested_value = self._extract_nested_value(item, keys)
                if nested_value not in (None, "", [], {}):
                    return nested_value
        return None

    def _normalize_embedding_value(self, value: Any) -> Any:
        if isinstance(value, tuple):
            return list(value)
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""
            if text[0] in "[{":
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return text
            return text
        return value

    def _coerce_face_value(self, value: Any) -> str:
        if isinstance(value, dict):
            nested = self._extract_nested_value(
                value,
                ("crop_face", "cropped_face", "face", "image", "image_url", "url", "file", "filename"),
            )
            return self._coerce_face_value(nested)
        if isinstance(value, (list, tuple)):
            return ""

        text = str(value or "").strip()
        if not text:
            return ""
        if text.lower().startswith(("http://", "https://", "data:image/")):
            return text
        if text.startswith("/"):
            return f"{self.api.base_url}{text}"
        if text.startswith("api/"):
            return f"{self.api.base_url}/{text}"
        return text

    def _request_embedding_payload(self, image_path: str) -> Any:
        if not image_path:
            raise RuntimeError("Image path is required.")
        if not os.path.isfile(image_path):
            raise RuntimeError(f"Image file not found: {image_path}")

        url = self._full_url("/api/v1/face_image/get_embedding")
        content_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        try:
            with open(image_path, "rb") as handle:
                response = self.api.client.request(
                    "POST",
                    url,
                    files={
                        "face_file": (
                            os.path.basename(image_path),
                            handle,
                            content_type,
                        )
                    },
                    headers=self._auth_headers(),
                    timeout=self.api.timeout,
                )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            detail = (exc.response.text or "").strip()
            raise RuntimeError(
                f"Embedding request failed [{exc.response.status_code}] POST {url}. {detail}".strip()
            ) from exc
        except httpx.RequestError as exc:
            raise RuntimeError(f"Unable to reach API at {url}: {exc}") from exc

        payload = self._parse_response(response)
        message = self._extract_message(payload, "")
        if message and "no face" in message.strip().lower():
            raise RuntimeError(message.strip())
        self._raise_if_failed(payload)
        return payload

    def _image_request_fields(self, image_path: str) -> Dict[str, Any]:
        fields: Dict[str, Any] = self._image_json_fields(image_path)
        payload = self._request_embedding_payload(image_path)

        embedding = None
        if isinstance(payload, list):
            embedding = payload
        elif isinstance(payload, dict):
            embedding = self._extract_nested_value(
                payload,
                ("embedding", "embeddings", "face_embedding", "vector"),
            )
        else:
            embedding = payload
        embedding = self._normalize_embedding_value(embedding)
        if embedding in (None, "", [], {}):
            raise RuntimeError("Embedding API did not return an embedding for the selected face image.")

        crop_face = self._coerce_face_value(
            self._extract_nested_value(
                payload,
                ("crop_face", "cropped_face", "face_crop", "crop", "image", "image_url", "url", "file", "filename"),
            )
        )
        if crop_face:
            fields["crop_face"] = crop_face
        fields["embedding"] = embedding
        return fields

    def _multipart_request(
        self,
        method: str,
        paths: Sequence[str],
        image_path: str,
        payload: Dict[str, Any] | None = None,
        field_names: Sequence[str] = ("face", "image", "file"),
    ) -> Any:
        if not image_path:
            raise RuntimeError("Image path is required.")
        if not os.path.isfile(image_path):
            raise RuntimeError(f"Image file not found: {image_path}")

        form_fields = self._stringify_form_fields(payload or {})
        content_type = mimetypes.guess_type(image_path)[0] or "application/octet-stream"
        last_exc: Exception | None = None

        for path in paths:
            url = self._full_url(path)
            for field_name in field_names:
                try:
                    with open(image_path, "rb") as handle:
                        response = self.api.client.request(
                            method.upper(),
                            url,
                            data=form_fields,
                            files={
                                field_name: (
                                    os.path.basename(image_path),
                                    handle,
                                    content_type,
                                )
                            },
                            headers=self._auth_headers(),
                            timeout=self.api.timeout,
                        )
                        response.raise_for_status()
                    payload_data = self._parse_response(response)
                    self._raise_if_failed(payload_data)
                    return payload_data
                except Exception as exc:
                    last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Unable to upload image.")

    def _parse_response(self, response: httpx.Response) -> Any:
        text = response.text.strip()
        if not text:
            return {}
        try:
            return response.json()
        except ValueError:
            return {"message": text}

    def _payload_to_dict(self, payload: Dict[str, Any] | FaceWhitelistPayload) -> Dict[str, Any]:
        data = payload.to_dict() if isinstance(payload, FaceWhitelistPayload) else dict(payload or {})
        cleaned: Dict[str, Any] = {}
        for key, value in data.items():
            if value in (None, ""):
                continue
            if isinstance(value, list) and not value:
                continue
            cleaned[key] = value
        return cleaned

    def list_entries(self) -> List[FaceWhitelistEntry]:
        payload = self._request_with_fallback(
            (
                ("GET", "/api/v1/face_whitelists/"),
                ("GET", "/api/v1/face_whitelists"),
            )
        )
        entries: List[FaceWhitelistEntry] = []
        for item in self._extract_items(payload):
            entries.append(FaceWhitelistEntry.from_dict(self._normalize_entry(item)))
        return entries

    def create_entry(
        self,
        payload: Dict[str, Any] | FaceWhitelistPayload,
        image_path: Optional[str] = None,
    ) -> tuple[str, str]:
        data = self._payload_to_dict(payload)
        paths = ("/api/v1/face_whitelists/create", "/api/v1/face_whitelists/create/")

        if image_path:
            image_fields = self._image_request_fields(image_path)
            upload_data = dict(data)
            upload_data.update(image_fields)
            try:
                response = self._multipart_request("POST", paths, image_path, payload=upload_data)
                return (
                    self._extract_message(response, "Whitelist person created successfully."),
                    self._extract_person_id(response),
                )
            except LowSimilarityError:
                raise
            except Exception:
                data.update(image_fields)

        response = self._request_with_fallback((( "POST", path) for path in paths), data=data)
        return (
            self._extract_message(response, "Whitelist person created successfully."),
            self._extract_person_id(response),
        )

    def update_entry(self, person_id: str, payload: Dict[str, Any] | FaceWhitelistPayload) -> str:
        data = self._payload_to_dict(payload)
        response = self._request_with_fallback(
            (
                ("PATCH", f"/api/v1/face_whitelists/update/{person_id}"),
                ("PATCH", f"/api/v1/face_whitelists/update/{person_id}/"),
            ),
            data=data,
        )
        return self._extract_message(response, "Whitelist person updated successfully.")

    def delete_entry(self, person_id: str) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/face_whitelists/delete/{person_id}"),
                ("DELETE", f"/api/v1/face_whitelists/delete/{person_id}/"),
            )
        )
        return self._extract_message(response, "Whitelist person deleted successfully.")

    def list_templates(self, person_id: str) -> List[FaceWhitelistTemplate]:
        payload = self._request_with_fallback(
            (
                ("GET", f"/api/v1/face_whitelists/templates/{person_id}"),
                ("GET", f"/api/v1/face_whitelists/templates/{person_id}/"),
            )
        )
        templates: List[FaceWhitelistTemplate] = []
        for item in self._extract_templates(payload):
            templates.append(FaceWhitelistTemplate.from_dict(self._normalize_template(item)))
        return templates

    def add_image(self, person_id: str, image_path: str) -> str:
        paths = (
            f"/api/v1/face_whitelists/add_image/{person_id}",
            f"/api/v1/face_whitelists/add_image/{person_id}/",
        )
        image_fields = self._image_request_fields(image_path)
        try:
            response = self._multipart_request("POST", paths, image_path, payload=image_fields)
            return self._extract_message(response, "Face image added successfully.")
        except LowSimilarityError:
            raise
        except Exception:
            response = self._request_with_fallback((( "POST", path) for path in paths), data=image_fields)
            return self._extract_message(response, "Face image added successfully.")

    def delete_template_image(self, person_id: str, template_id: str) -> str:
        response = self._request_with_fallback(
            (
                ("DELETE", f"/api/v1/face_whitelists/delete_image/{person_id}/{template_id}"),
                ("DELETE", f"/api/v1/face_whitelists/delete_image/{person_id}/{template_id}/"),
            )
        )
        return self._extract_message(response, "Template image deleted successfully.")
