from dataclasses import dataclass


@dataclass
class ActivationInfo:
    camera_limit: int = -1
    device_id: str = ""
    server_address: str = ""
    expire_date: str = ""
    activated: bool = False
