from dataclasses import dataclass
from typing import Optional

@dataclass
class Client:
    id: int
    name: str
    ip: str
    type: str
    port: int = 0
    save_path: str = ""
    is_local: bool = True
    online: Optional[bool] = None
    device_id: str = ""
    server_address: str = ""
    camera_limit: int = -1
    expire_date: str = ""
    activated: bool = False

@dataclass
class ClientResponce:
    id: int
    name: str
    ip: str
    port: int
    save_path: str
    type: str
    is_local: bool
    online: Optional[bool] = None
    device_id: str = ""
    server_address: str = ""
    camera_limit: int = -1
    expire_date: str = ""
    activated: bool = False
