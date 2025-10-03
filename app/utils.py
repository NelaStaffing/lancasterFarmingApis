from typing import Tuple
import io
import numpy as np
import cv2
from PIL import Image


def bytes_to_cv2_image(data: bytes) -> np.ndarray:
    """Decode bytes to an OpenCV BGR image."""
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Could not decode image bytes")
    return img


def cv2_to_png_bytes(img_bgr: np.ndarray) -> bytes:
    """Encode OpenCV BGR image to PNG bytes."""
    success, buf = cv2.imencode('.png', img_bgr)
    if not success:
        raise RuntimeError("Failed to encode image to PNG")
    return buf.tobytes()


def ensure_gray(img_bgr: np.ndarray) -> np.ndarray:
    if len(img_bgr.shape) == 2:
        return img_bgr
    return cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)


def read_image_file(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"Could not read image at {path}")
    return img


def clamp_bbox(x: int, y: int, w: int, h: int, width: int, height: int) -> Tuple[int, int, int, int]:
    x = max(0, min(x, width - 1))
    y = max(0, min(y, height - 1))
    w = max(1, min(w, width - x))
    h = max(1, min(h, height - y))
    return x, y, w, h


def rect_from_logo_relative(
    image_shape: Tuple[int, int, int] | Tuple[int, int],
    logo_bbox: Tuple[int, int, int, int],
    left_mul: float,
    top_mul: float,
    right_mul: float,
    bottom_mul: float,
) -> Tuple[int, int, int, int]:
    """Compute a rectangle using distances relative to the detected logo size.

    The distances are multipliers of the logo width/height measured from the
    logo's bounding box:
      - left_mul:  x1 = logo.x + left_mul * logo.w
      - top_mul:   y1 = logo.y + top_mul * logo.h
      - right_mul: x2 = logo.x + logo.w + right_mul * logo.w
      - bottom_mul:y2 = logo.y + logo.h + bottom_mul * logo.h

    Negative values move left/up; positive move right/down. The result is
    clamped to the image bounds.
    """
    if len(image_shape) >= 2:
        height, width = image_shape[0], image_shape[1]
    else:
        raise ValueError("Invalid image shape")

    x, y, w, h = logo_bbox
    x1 = int(round(x + left_mul * w))
    y1 = int(round(y + top_mul * h))
    x2 = int(round(x + w + right_mul * w))
    y2 = int(round(y + h + bottom_mul * h))

    x_min, y_min = min(x1, x2), min(y1, y2)
    x_max, y_max = max(x1, x2), max(y1, y2)
    bb_w = x_max - x_min
    bb_h = y_max - y_min
    return clamp_bbox(x_min, y_min, bb_w, bb_h, width, height)


def crop_to_bbox(img_bgr: np.ndarray, bbox: Tuple[int, int, int, int]) -> np.ndarray:
    """Crop an image to the given bbox (x,y,w,h) with clamping."""
    H, W = img_bgr.shape[:2]
    x, y, w, h = clamp_bbox(bbox[0], bbox[1], bbox[2], bbox[3], W, H)
    return img_bgr[y:y+h, x:x+w]
