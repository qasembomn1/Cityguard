from __future__ import annotations

import os
import urllib.parse
from typing import Any, List, Tuple

from app.api.api_service import ApiService


def _time_to_seconds(value: str) -> int:
    parts = [part.strip() for part in str(value or "").split(":")]
    if len(parts) != 3:
        return 0
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = int(parts[2])
    except (TypeError, ValueError):
        return 0
    return max(0, (hours * 3600) + (minutes * 60) + seconds)


def _seconds_to_hms(value: int) -> str:
    total = max(0, int(value))
    hours = total // 3600
    minutes = (total % 3600) // 60
    seconds = total % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


class PlaybackService:
    def __init__(self, api: ApiService | None = None) -> None:
        self.api = api or ApiService(os.getenv("Base_URL"))
        self.playlist_base_url = self._resolve_playlist_base_url()

    def available_days(self, camera_id: int | str, year_month: str) -> List[str]:
        payload = self.api.request(
            "POST",
            "/api/v1/camera/available_days",
            params={"camera_id": str(camera_id), "year_month": year_month},
            auth=True,
        )
        return self._extract_days(payload)

    def available_range(self, camera_id: int | str, date: str) -> List[Tuple[int, int]]:
        payload = self.api.request(
            "POST",
            "/api/v1/camera/available_range",
            params={"camera_id": str(camera_id), "date": date},
            auth=True,
        )
        return self._extract_ranges(payload)

    def build_playlist_url(
        self,
        camera_id: int | str,
        date: str,
        current_time: int | str | None = None,
    ) -> str:
        params = {
            "camera_id": str(camera_id),
            "date": date,
        }
        if current_time is not None:
            if isinstance(current_time, int):
                params["current_time"] = _seconds_to_hms(current_time)
            else:
                params["current_time"] = str(current_time)
        query = urllib.parse.urlencode(params)
        return f"{self.playlist_base_url}/playlist.m3u8?{query}"

    def _resolve_playlist_base_url(self) -> str:
        explicit = (
            os.getenv("PLAYBACK_BASE_URL")
            or os.getenv("PLAYBACK_STREAM_BASE_URL")
            or os.getenv("PLAYLIST_BASE_URL")
            or ""
        ).strip()
        if explicit:
            return explicit.rstrip("/")

        parsed = urllib.parse.urlsplit(self.api.base_url)
        scheme = parsed.scheme or "http"
        host = parsed.hostname or "127.0.0.1"
        return f"{scheme}://{host}:7000"

    def _extract_days(self, payload: Any) -> List[str]:
        candidates: list[str] = []

        def collect(value: Any) -> None:
            if isinstance(value, str):
                text = value.strip()
                if len(text) == 10 and text[4] == "-" and text[7] == "-":
                    candidates.append(text)
                return
            if isinstance(value, list):
                for item in value:
                    collect(item)
                return
            if isinstance(value, dict):
                for key in ("dates", "available_days", "items", "data", "result", "results", "payload"):
                    if key in value:
                        collect(value.get(key))

        collect(payload)
        return sorted({item for item in candidates})

    def _extract_ranges(self, payload: Any) -> List[Tuple[int, int]]:
        entries: list[dict[str, Any]] = []

        def collect(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        entries.append(item)
                return
            if isinstance(value, dict):
                for key in ("ranges", "items", "data", "result", "results", "payload"):
                    nested = value.get(key)
                    if isinstance(nested, list):
                        collect(nested)
                    elif isinstance(nested, dict):
                        collect(nested)

        collect(payload)

        ranges: list[Tuple[int, int]] = []
        for item in entries:
            start_raw = item.get("start_minute") or item.get("start")
            end_raw = item.get("end_minute") or item.get("end")
            if start_raw is None or end_raw is None:
                continue

            if isinstance(start_raw, (int, float)) and isinstance(end_raw, (int, float)):
                start = max(0, int(start_raw))
                end = max(start, int(end_raw))
            else:
                start = _time_to_seconds(str(start_raw))
                end = _time_to_seconds(str(end_raw))
                if end < start:
                    end = 86400

            if end > start:
                ranges.append((start, end))

        ranges.sort(key=lambda item: (item[0], item[1]))
        return ranges
