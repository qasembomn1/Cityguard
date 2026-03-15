from __future__ import annotations

from typing import Any

from app.constants._init_ import Constants
from app.utils.digits import normalize_ascii_digits


_REGION_NAME_OVERRIDES = {
    "BAGHDAD": "Baghdad",
    "NAINAWA": "Nineveh",
    "MYSAN": "Maysan",
    "AL-BASRAH": "Basra",
    "AL-ANBAR": "Anbar",
    "AL-QADSIAH": "Al-Qadisiyah",
    "AL-MUTHANA": "Muthanna",
    "BABL": "Babylon",
    "KARBALA": "Karbala",
    "DIALAH": "Diyala",
    "SULIMANIAH": "Sulaymaniyah",
    "ERBIL": "Erbil",
    "HALABJA": "Halabja",
    "DUHOK": "Duhok",
    "KARKUK": "Kirkuk",
    "SALAH-ALDIN": "Salahaddin",
    "DHE-QAR": "Dhi Qar",
    "NAJAF": "Najaf",
    "WAST": "Wasit",
}


def _as_text(value: Any) -> str:
    return normalize_ascii_digits(value).strip()


def _region_code_text(value: Any) -> str:
    text = _as_text(value)
    if not text.isdigit():
        return ""
    return f"{int(text):02d}"


REGION_CODE_MAP: dict[str, str] = {
    code: _as_text(raw_name)
    for raw_code, raw_name in getattr(Constants, "Region_Map", {}).items()
    if (code := _region_code_text(raw_code)) and _as_text(raw_name)
}


def region_label(value: Any) -> str:
    text = _as_text(value)
    if not text:
        return ""
    return _REGION_NAME_OVERRIDES.get(text.upper(), text)


def region_options() -> list[str]:
    seen: set[str] = set()
    options: list[str] = []
    for code in sorted(REGION_CODE_MAP, key=int):
        label = region_label(REGION_CODE_MAP[code])
        if label and label not in seen:
            seen.add(label)
            options.append(label)
    return options


def plate_region(region_value: Any, plate_value: Any) -> str:
    explicit = region_label(region_value)
    if explicit:
        return explicit

    plate = _as_text(plate_value).replace(" ", "")
    if len(plate) < 3:
        return "Unknown"

    code = plate[:2]
    letter = plate[2:3].upper()
    if not code.isdigit() or not letter.isascii() or not letter.isalpha():
        return "Unknown"

    mapped = REGION_CODE_MAP.get(code)
    return region_label(mapped) if mapped else "Unknown"
