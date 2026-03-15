from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ScreenCamera:
    camera_id: int
    index: int
    name: str = ""
    camera_ip: str = ""


@dataclass
class Screen:
    screen_type: int
    cameras: list[ScreenCamera] = field(default_factory=list)


@dataclass
class ScreenResponse:
    id: int
    screen_type: int
    created_at: Optional[datetime] = None
    cameras: list[ScreenCamera] = field(default_factory=list)

    @property
    def camera_ids(self) -> list[int]:
        return [item.camera_id for item in self.cameras if item.camera_id > 0]


CameraScreen = ScreenCamera
ScreenResponce = ScreenResponse
