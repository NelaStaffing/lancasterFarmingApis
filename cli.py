import argparse
import os
from pathlib import Path

import cv2

from app.utils import read_image_file, rect_from_logo_relative, clamp_bbox
from app.detect import detect_logo, draw_bbox


def main():
    p = argparse.ArgumentParser(description="Annotate images with detected logo bounding box")
    p.add_argument("image", help="Path to image or folder of images")
    p.add_argument("--template", required=True, help="Path to logo template image")
    p.add_argument("--method", default="auto", choices=["auto", "orb", "template"]) 
    p.add_argument("--out", default="out", help="Output folder")
    p.add_argument("--thickness", type=int, default=4)
    # optional secondary rectangle (normalized to logo size)
    p.add_argument("--section-left-mul", type=float)
    p.add_argument("--section-top-mul", type=float)
    p.add_argument("--section-right-mul", type=float)
    p.add_argument("--section-bottom-mul", type=float)
    p.add_argument("--section-width-mul", type=float)
    p.add_argument("--section-height-mul", type=float)
    p.add_argument("--section-thickness", type=int, default=3)
    args = p.parse_args()

    in_path = Path(args.image)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    paths = []
    if in_path.is_dir():
        for ext in ("*.png", "*.jpg", "*.jpeg", "*.tif", "*.tiff", "*.bmp"):
            paths.extend(in_path.glob(ext))
    else:
        paths = [in_path]

    tmpl = read_image_file(args.template)

    for ip in paths:
        img = read_image_file(str(ip))
        res = detect_logo(img, tmpl, method=args.method)
        if res is None:
            print(f"[WARN] Logo not found in {ip}")
            continue
        annotated = draw_bbox(img, tuple(res["bbox"]), thickness=args.thickness)

        # Optional secondary rectangle
        lm = args.section_left_mul
        tm = args.section_top_mul
        if lm is not None and tm is not None:
            if args.section_right_mul is not None and args.section_bottom_mul is not None:
                sec_bbox = rect_from_logo_relative(
                    img.shape, tuple(res["bbox"]), lm, tm, args.section_right_mul, args.section_bottom_mul
                )
                annotated = draw_bbox(annotated, sec_bbox, color=(0, 255, 0), thickness=args.section_thickness)
            elif args.section_width_mul is not None and args.section_height_mul is not None:
                x, y, w, h = tuple(res["bbox"])
                x1 = int(round(x + lm * w))
                y1 = int(round(y + tm * h))
                x2 = int(round(x1 + args.section_width_mul * w))
                y2 = int(round(y1 + args.section_height_mul * h))
                sec_bbox = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]
                H, W = img.shape[:2]
                sec_bbox = clamp_bbox(sec_bbox[0], sec_bbox[1], sec_bbox[2], sec_bbox[3], W, H)
                annotated = draw_bbox(annotated, sec_bbox, color=(0, 255, 0), thickness=args.section_thickness)
        out_path = out_dir / f"{ip.stem}_annotated.png"
        cv2.imwrite(str(out_path), annotated)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
