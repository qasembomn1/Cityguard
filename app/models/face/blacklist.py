from __future__ import annotations

from app.models.face.whitelist import FaceWhitelistEntry, FaceWhitelistPayload, FaceWhitelistTemplate


FaceBlacklistEntry = FaceWhitelistEntry
FaceBlacklistPayload = FaceWhitelistPayload
FaceBlacklistTemplate = FaceWhitelistTemplate

__all__ = [
    "FaceBlacklistEntry",
    "FaceBlacklistPayload",
    "FaceBlacklistTemplate",
]
