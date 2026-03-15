from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AccessControlType:
    num_of_relay: int


@dataclass
class AccessControl:
    id: int
    name: str
    ac_type: AccessControlType

