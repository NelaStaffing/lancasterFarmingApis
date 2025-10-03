from __future__ import annotations
from typing import Dict, List, Optional, Tuple
import math
import numpy as np
import cv2

from .utils import ensure_gray, clamp_bbox


class DetectionResult(dict):
    """Dictionary containing detection info.
    keys: method, confidence, bbox[x,y,w,h], polygon[list of (x,y)]
    """


def detect_with_orb(img_bgr: np.ndarray, tmpl_bgr: np.ndarray, min_matches: int = 10) -> Optional[DetectionResult]:
    img_gray = ensure_gray(img_bgr)
    tmpl_gray = ensure_gray(tmpl_bgr)

    # ORB features
    orb = cv2.ORB_create(nfeatures=2000, scaleFactor=1.2, nlevels=8)
    kp1, des1 = orb.detectAndCompute(tmpl_gray, None)
    kp2, des2 = orb.detectAndCompute(img_gray, None)
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return None

    bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=False)
    matches = bf.knnMatch(des1, des2, k=2)

    good: List[cv2.DMatch] = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good.append(m)

    if len(good) < min_matches:
        return None

    src_pts = np.float32([kp1[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp2[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
    if H is None:
        return None

    h, w = tmpl_gray.shape[:2]
    corners = np.float32([[0, 0], [w, 0], [w, h], [0, h]]).reshape(-1, 1, 2)
    proj = cv2.perspectiveTransform(corners, H).reshape(-1, 2)

    xs, ys = proj[:, 0], proj[:, 1]
    x_min, x_max = int(np.min(xs)), int(np.max(xs))
    y_min, y_max = int(np.min(ys)), int(np.max(ys))

    Hh, Hw = img_gray.shape[:2]
    x, y, bw, bh = clamp_bbox(x_min, y_min, x_max - x_min, y_max - y_min, Hw, Hh)

    inlier_ratio = float(np.sum(mask)) / float(len(mask)) if mask is not None else 0.0

    return DetectionResult(
        method="orb",
        confidence=float(min(1.0, max(0.0, inlier_ratio))),
        bbox=[int(x), int(y), int(bw), int(bh)],
        polygon=[[int(pt[0]), int(pt[1])] for pt in proj.tolist()],
    )


def detect_with_template(img_bgr: np.ndarray, tmpl_bgr: np.ndarray, scales: Optional[List[float]] = None) -> Optional[DetectionResult]:
    img_gray = ensure_gray(img_bgr)
    tmpl_gray = ensure_gray(tmpl_bgr)

    # Edge-based matching is often more robust on scans
    tmpl_edges = cv2.Canny(tmpl_gray, 50, 150)
    best = None
    best_val = -1.0

    if scales is None:
        scales = [round(s, 2) for s in np.linspace(0.4, 2.0, num=33)]

    for s in scales:
        th = max(1, int(3 / s))
        img_edges = cv2.Canny(img_gray, 50, 150)
        tmpl_scaled = cv2.resize(tmpl_edges, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        th, tw = tmpl_scaled.shape[:2]
        if th >= img_edges.shape[0] or tw >= img_edges.shape[1] or th < 8 or tw < 8:
            continue
        res = cv2.matchTemplate(img_edges, tmpl_scaled, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
        if max_val > best_val:
            best_val = float(max_val)
            x, y = max_loc
            best = (x, y, tw, th, max_val)

    if best is None:
        return None

    x, y, w, h, score = best
    Hh, Hw = img_gray.shape[:2]
    x, y, w, h = clamp_bbox(x, y, w, h, Hw, Hh)

    polygon = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
    return DetectionResult(
        method="template",
        confidence=float(score),
        bbox=[int(x), int(y), int(w), int(h)],
        polygon=polygon,
    )


def detect_logo(img_bgr: np.ndarray, tmpl_bgr: np.ndarray, method: str = "auto") -> Optional[DetectionResult]:
    method = (method or "auto").lower()

    if method in ("auto", "orb"):
        res = detect_with_orb(img_bgr, tmpl_bgr)
        if res is not None:
            return res
        if method == "orb":
            return None

    # fallback
    return detect_with_template(img_bgr, tmpl_bgr)


def draw_bbox(img_bgr: np.ndarray, bbox: Tuple[int, int, int, int], color=(0, 0, 255), thickness: int = 4) -> np.ndarray:
    x, y, w, h = bbox
    out = img_bgr.copy()
    cv2.rectangle(out, (x, y), (x + w, y + h), color, thickness)
    return out
