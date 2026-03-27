from __future__ import annotations

import os
from typing import Any, Dict, Iterable, List, Optional

from app.api.api_service import ApiService
from app.models.face.search import FaceEmbeddingResult, FaceSearchPayload, FaceSearchResult
from app.services.home.face_whitelist_service import FaceWhitelistService
from app.utils.list import extract_dict_list


class FaceSearchService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))
        self._embedding_helper = FaceWhitelistService(self.api)

    def _request_with_fallback(
        self,
        attempts: Iterable[tuple[str, str, Optional[Dict[str, Any]], Optional[Dict[str, Any]]]],
    ) -> Any:
        last_exc: Exception | None = None
        for method, path, data, params in attempts:
            try:
                return self.api.request(
                    method=method,
                    url=path,
                    data=data,
                    params=params,
                    auth=True,
                )
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("No face search API attempts configured.")

    def _extract_items(self, payload: Any) -> List[Dict[str, Any]]:
        items = extract_dict_list(payload, keys=("items", "data", "results", "records", "detections"))
        if items:
            return items
        if isinstance(payload, dict):
            for key in ("data", "result", "payload"):
                nested = payload.get(key)
                nested_items = extract_dict_list(
                    nested,
                    keys=("items", "data", "results", "records", "detections"),
                )
                if nested_items:
                    return nested_items
            if any(key in payload for key in ("cam_id", "camera_id", "gender", "age", "filename")):
                return [payload]
        elif isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        return []

    def _extract_nested_value(self, payload: Any, keys: Iterable[str]) -> Any:
        return self._embedding_helper._extract_nested_value(payload, tuple(keys))

    def _coerce_face_value(self, value: Any) -> str:
        return self._embedding_helper._coerce_face_value(value)

    def _normalize_embedding_value(self, value: Any) -> Any:
        return self._embedding_helper._normalize_embedding_value(value)

    def _embedding_result_from_payload(self, payload: Any, fallback_image_url: str = "") -> FaceEmbeddingResult:
        embedding = self._embedding_helper._extract_embedding_value(payload)
        if embedding in (None, "", [], {}):
            raise RuntimeError("Embedding API did not return an embedding value.")

        crop_image_url = self._embedding_helper._extract_face_payload_value(payload, crop=True)
        image_url = self._embedding_helper._extract_face_payload_value(payload, crop=False)
        normalized_image_url = image_url or fallback_image_url
        normalized_crop_url = crop_image_url or image_url or fallback_image_url
        return FaceEmbeddingResult(
            embedding=embedding,
            image_url=normalized_image_url,
            crop_image_url=normalized_crop_url,
            raw=payload,
        )

    def search_faces(self, payload: Dict[str, Any] | FaceSearchPayload) -> List[FaceSearchResult]:
        data = payload.to_dict() if isinstance(payload, FaceSearchPayload) else dict(payload or {})
        response = self._request_with_fallback(
            (
                ("POST", "/api/v1/face_search/", data, None),
                ("POST", "/api/v1/face_search", data, None),
            )
        )
        return [
            FaceSearchResult.from_dict(item)
            for item in self._extract_items(response)
            if isinstance(item, dict)
        ]

    def get_embedding(self, image_path: str) -> FaceEmbeddingResult:
        fallback_image_url = self._embedding_helper._image_json_fields(image_path).get("face", "")
        payload = self._embedding_helper._request_embedding_payload(image_path)
        return self._embedding_result_from_payload(payload, fallback_image_url=fallback_image_url)

    def get_embedding_by_url(self, image_url: str) -> FaceEmbeddingResult:
        normalized = str(image_url or "").strip()
        if not normalized:
            raise RuntimeError("Image URL is required.")

        response = self._request_with_fallback(
            (
                ("GET", "/api/v1/face_image/get_embedding_by_url", None, {"url": normalized}),
                ("GET", "/api/v1/face_image/get_embedding_by_url/", None, {"url": normalized}),
                ("GET", "/api/v1/face_image/get_embedding_by_url", None, {"file": normalized}),
                ("GET", "/api/v1/face_image/get_embedding_by_url/", None, {"file": normalized}),
                ("GET", "/api/v1/face_image/get_embedding_by_url", None, {"image_url": normalized}),
                ("GET", "/api/v1/face_image/get_embedding_by_url/", None, {"image_url": normalized}),
            )
        )
        return self._embedding_result_from_payload(response, fallback_image_url=normalized)
