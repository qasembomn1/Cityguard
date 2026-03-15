from __future__ import annotations

from typing import Any


_ARABIC_DIGIT_TRANSLATION = str.maketrans(
    "٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹",
    "01234567890123456789",
)


def normalize_ascii_digits(value: Any) -> str:
    return str(value or "").translate(_ARABIC_DIGIT_TRANSLATION)
