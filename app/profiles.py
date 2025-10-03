from __future__ import annotations
import json
import os
from typing import Dict, Optional, Literal

from pydantic import BaseModel, Field

from .utils import rect_from_logo_relative, clamp_bbox


PROFILE_FILE = os.getenv(
    "LOGO_PROFILES_PATH",
    os.path.join(os.path.dirname(__file__), "profiles.json"),
)


class Profile(BaseModel):
    name: str = Field(..., description="Unique profile name")
    mode: Literal["edge", "size"] = Field("edge")
    # common
    left_mul: float
    top_mul: float
    # edge mode extras
    right_mul: Optional[float] = None
    bottom_mul: Optional[float] = None
    # size mode extras
    width_mul: Optional[float] = None
    height_mul: Optional[float] = None
    section_thickness: int = 3

    def compute_bbox(self, image_shape, logo_bbox):
        if self.mode == "edge":
            if self.right_mul is None or self.bottom_mul is None:
                raise ValueError("edge mode requires right_mul and bottom_mul")
            return rect_from_logo_relative(
                image_shape, logo_bbox,
                self.left_mul, self.top_mul, self.right_mul, self.bottom_mul,
            )
        else:
            if self.width_mul is None or self.height_mul is None:
                raise ValueError("size mode requires width_mul and height_mul")
            x, y, w, h = logo_bbox
            x1 = int(round(x + self.left_mul * w))
            y1 = int(round(y + self.top_mul * h))
            x2 = int(round(x1 + self.width_mul * w))
            y2 = int(round(y1 + self.height_mul * h))
            bb = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]
            H, W = image_shape[0], image_shape[1]
            return clamp_bbox(bb[0], bb[1], bb[2], bb[3], W, H)


def load_profiles() -> Dict[str, dict]:
    if not os.path.exists(PROFILE_FILE):
        return {}
    try:
        with open(PROFILE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            return {}
    except Exception:
        return {}


def save_profiles(data: Dict[str, dict]) -> None:
    os.makedirs(os.path.dirname(PROFILE_FILE), exist_ok=True)
    with open(PROFILE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def get_profile(name: str) -> Optional[Profile]:
    data = load_profiles()
    p = data.get(name)
    if not p:
        return None
    return Profile(**p)


def upsert_profile(profile: Profile) -> Profile:
    data = load_profiles()
    data[profile.name] = profile.model_dump()
    save_profiles(data)
    return profile


def delete_profile(name: str) -> bool:
    data = load_profiles()
    if name in data:
        del data[name]
        save_profiles(data)
        return True
    return False
