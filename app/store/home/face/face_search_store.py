from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models.face.search import FaceEmbeddingResult, FaceSearchPayload, FaceSearchResult
from app.services.home.face_search_service import FaceSearchService
from app.store._init_ import BaseStore


class FaceSearchStore(BaseStore):
    def __init__(self, service: FaceSearchService) -> None:
        super().__init__()
        self.service = service
        self.results: List[FaceSearchResult] = []
        self.loading = False
        self.embedding_result: Optional[FaceEmbeddingResult] = None

    def clear(self) -> None:
        self.results = []
        self.changed.emit()

    def clear_embedding(self) -> None:
        self.embedding_result = None
        self.changed.emit()

    def search(self, payload: Dict[str, Any]) -> List[FaceSearchResult]:
        self.loading = True
        self.changed.emit()
        try:
            request = FaceSearchPayload(**payload)
            self.results = self.service.search_faces(request)
            return list(self.results)
        except Exception as exc:
            self.results = []
            self.emit_error(str(exc))
            return []
        finally:
            self.loading = False
            self.changed.emit()

    def get_embedding(self, image_path: str) -> Optional[FaceEmbeddingResult]:
        try:
            self.embedding_result = self.service.get_embedding(image_path)
            self.changed.emit()
            return self.embedding_result
        except Exception as exc:
            self.embedding_result = None
            self.emit_error(str(exc))
            return None

    def get_embedding_by_url(self, image_url: str) -> Optional[FaceEmbeddingResult]:
        try:
            self.embedding_result = self.service.get_embedding_by_url(image_url)
            self.changed.emit()
            return self.embedding_result
        except Exception as exc:
            self.embedding_result = None
            self.emit_error(str(exc))
            return None
