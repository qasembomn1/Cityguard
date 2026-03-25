from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class Camera:
    id: int
    name: str
    client_id_1: Optional[int] = None
    client_id_2: Optional[int] = None
    client_id_3: Optional[int] = None
    client_1: Optional[Dict[str, Any]] = None
    client_2: Optional[Dict[str, Any]] = None
    client_3: Optional[Dict[str, Any]] = None
    access_control_id: Optional[int] = None
    door_number: Optional[int] = None
    roi: str = ""
    map_pos: str = ""
    is_record: bool = True
    is_process: bool = False
    is_live: bool = True
    is_ptz: bool = False
    forward_stream: bool = False
    is_ai_cam: bool = False
    fps_delay: int = 5
    process_type: str = "lpr"
    camera_type_id: Optional[int] = None
    camera_ip: str = ""
    camera_username: str = ""
    camera_password: str = ""
    camera_port: int = 554
    face_person_count: bool = False
    face_color_detection: bool = False
    face_min_size: int = 5
    face_max_size: int = 40
    face_show_rect: bool = False
    face_count_line: str = ""
    lpr_show_rect: bool = False
    lpr_min_size: int = 5
    lpr_max_size: int = 40
    lpr_min_confidence: int = 70
    image: Optional[str] = None
    camera_type: Optional[Dict[str, Any]] = None
    online: bool = False
    streaming_fps: int = 0
    processing_fps: int = 0
    total_in: int = 0
    total_out: int = 0


@dataclass
class CameraResponce:
    id: int
    name: str
    ip: str
    client_id_1: Optional[int] = None
    client_id_2: Optional[int] = None
    client_id_3: Optional[int] = None
    process_type: str = "lpr"
    access_control_id: Optional[int] = None
    door_number: Optional[int] = None
    streaming_fps: int = 0
    processing_fps: int = 0
    total_in: int = 0
    total_out: int = 0
    face_show_rect: bool = True

@dataclass
class CameraType:
    id: int = 0
    name: str = ""
    protocol: str = ""
    main_url: str = ""
    sub_url: str = ""
    ptz_url: str = ""
    network_url: str = ""

    def to_payload(self) -> Dict[str, str]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "main_url": self.main_url,
            "sub_url": self.sub_url,
            "ptz_url": self.ptz_url,
            "network_url": self.network_url,
        }
