import os
import io
import json
import zipfile
from typing import Optional, List

import uvicorn
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse, PlainTextResponse

from .utils import (
    bytes_to_cv2_image,
    cv2_to_png_bytes,
    read_image_file,
    rect_from_logo_relative,
    clamp_bbox,
    crop_to_bbox,
)
from .detect import detect_logo, draw_bbox
from .profiles import Profile, get_profile, upsert_profile, delete_profile, load_profiles

APP_TITLE = "Logo Locator API"
DEFAULT_TEMPLATE_PATH = os.getenv("LOGO_TEMPLATE_PATH", os.path.join(os.path.dirname(__file__), "assets", "logo.png"))

app = FastAPI(title=APP_TITLE)


@app.get("/health")
def health():
    return {"status": "ok"}


def _get_template_bytes(template_file: Optional[UploadFile]) -> bytes:
    if template_file is not None:
        return template_file.file.read()
    # try default
    if os.path.exists(DEFAULT_TEMPLATE_PATH):
        with open(DEFAULT_TEMPLATE_PATH, "rb") as f:
            return f.read()
    raise HTTPException(status_code=400, detail="No template provided and default template not found. Upload 'template' file or place one at app/assets/logo.png")


@app.post("/detect")
async def detect(
    image: UploadFile = File(..., description="Scanned form image"),
    template: Optional[UploadFile] = File(None, description="Logo template image (optional if default exists)"),
    method: str = Form("auto"),
):
    img_bytes = await image.read()
    tmpl_bytes = _get_template_bytes(template)

    img_bgr = bytes_to_cv2_image(img_bytes)
    tmpl_bgr = bytes_to_cv2_image(tmpl_bytes)

    res = detect_logo(img_bgr, tmpl_bgr, method=method)
    if res is None:
        raise HTTPException(status_code=404, detail="Logo not found")

    h, w = img_bgr.shape[:2]
    payload = {
        "width": int(w),
        "height": int(h),
        **res,
    }
    return JSONResponse(payload)


@app.post("/annotate")
async def annotate(
    image: UploadFile = File(..., description="Scanned form image"),
    template: Optional[UploadFile] = File(None, description="Logo template image (optional if default exists)"),
    method: str = Form("auto"),
    thickness: int = Form(4),
    profile: Optional[str] = Form(None, description="Optional saved profile name"),
    # Optional secondary rectangle relative to logo
    section_left_mul: Optional[float] = Form(None, description="Left offset in multiples of logo width"),
    section_top_mul: Optional[float] = Form(None, description="Top offset in multiples of logo height"),
    section_right_mul: Optional[float] = Form(None, description="Right offset in multiples of logo width (edge mode)"),
    section_bottom_mul: Optional[float] = Form(None, description="Bottom offset in multiples of logo height (edge mode)"),
    section_width_mul: Optional[float] = Form(None, description="Width in multiples of logo width (size mode)"),
    section_height_mul: Optional[float] = Form(None, description="Height in multiples of logo height (size mode)"),
    section_thickness: int = Form(3),
):
    img_bytes = await image.read()
    tmpl_bytes = _get_template_bytes(template)

    img_bgr = bytes_to_cv2_image(img_bytes)
    tmpl_bgr = bytes_to_cv2_image(tmpl_bytes)

    res = detect_logo(img_bgr, tmpl_bgr, method=method)
    if res is None:
        raise HTTPException(status_code=404, detail="Logo not found")

    out = draw_bbox(img_bgr, tuple(res["bbox"]), thickness=thickness)

    # Optional second rectangle relative to logo, via profile or explicit params
    try:
        sec_bbox = None
        if profile:
            prof = get_profile(profile)
            if prof is None:
                raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
            sec_bbox = prof.compute_bbox(img_bgr.shape, tuple(res["bbox"]))
            section_thickness = prof.section_thickness if section_thickness is None else section_thickness
        elif section_left_mul is not None and section_top_mul is not None:
            if section_right_mul is not None and section_bottom_mul is not None:
                sec_bbox = rect_from_logo_relative(
                    img_bgr.shape, tuple(res["bbox"]),
                    section_left_mul, section_top_mul, section_right_mul, section_bottom_mul,
                )
            elif section_width_mul is not None and section_height_mul is not None:
                # size mode: build right/bottom from width/height multipliers
                x, y, w, h = tuple(res["bbox"])
                x1 = int(round(x + section_left_mul * w))
                y1 = int(round(y + section_top_mul * h))
                x2 = int(round(x1 + section_width_mul * w))
                y2 = int(round(y1 + section_height_mul * h))
                sec_bbox = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]
                # Clamp using image bounds
                H, W = img_bgr.shape[:2]
                sec_bbox = clamp_bbox(sec_bbox[0], sec_bbox[1], sec_bbox[2], sec_bbox[3], W, H)
        if sec_bbox is not None:
            out = draw_bbox(out, sec_bbox, color=(0, 255, 0), thickness=section_thickness)
    except Exception as e:
        # Keep API resilient: ignore bad section parameters and continue returning main annotation
        pass

    png = cv2_to_png_bytes(out)
    return StreamingResponse(iter([png]), media_type="image/png")


# Profiles management
@app.get("/profiles")
def list_profiles():
    return load_profiles()


@app.get("/profiles/{name}")
def get_profile_endpoint(name: str):
    p = get_profile(name)
    if p is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return p.model_dump()


@app.put("/profiles/{name}")
def upsert_profile_endpoint(name: str, profile: Profile):
    if profile.name != name:
        profile.name = name
    saved = upsert_profile(profile)
    return saved.model_dump()


@app.delete("/profiles/{name}")
def delete_profile_endpoint(name: str):
    ok = delete_profile(name)
    if not ok:
        raise HTTPException(status_code=404, detail="Profile not found")
    return {"deleted": name}


@app.post("/cut-section")
async def cut_section(
    image: UploadFile = File(..., description="Scanned form image"),
    template: Optional[UploadFile] = File(None, description="Logo template image (optional if default exists)"),
    method: str = Form("auto"),
    profile: Optional[str] = Form(None),
    # explicit params fallback
    section_left_mul: Optional[float] = Form(None),
    section_top_mul: Optional[float] = Form(None),
    section_right_mul: Optional[float] = Form(None),
    section_bottom_mul: Optional[float] = Form(None),
    section_width_mul: Optional[float] = Form(None),
    section_height_mul: Optional[float] = Form(None),
):
    img_bytes = await image.read()
    tmpl_bytes = _get_template_bytes(template)

    img_bgr = bytes_to_cv2_image(img_bytes)
    tmpl_bgr = bytes_to_cv2_image(tmpl_bytes)

    res = detect_logo(img_bgr, tmpl_bgr, method=method)
    if res is None:
        raise HTTPException(status_code=404, detail="Logo not found")

    sec_bbox = None
    if profile:
        prof = get_profile(profile)
        if prof is None:
            raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
        sec_bbox = prof.compute_bbox(img_bgr.shape, tuple(res["bbox"]))
    elif section_left_mul is not None and section_top_mul is not None:
        if section_right_mul is not None and section_bottom_mul is not None:
            sec_bbox = rect_from_logo_relative(
                img_bgr.shape, tuple(res["bbox"]),
                section_left_mul, section_top_mul, section_right_mul, section_bottom_mul,
            )
        elif section_width_mul is not None and section_height_mul is not None:
            x, y, w, h = tuple(res["bbox"])
            x1 = int(round(x + section_left_mul * w))
            y1 = int(round(y + section_top_mul * h))
            x2 = int(round(x1 + section_width_mul * w))
            y2 = int(round(y1 + section_height_mul * h))
            sec_bbox = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]
            H, W = img_bgr.shape[:2]
            sec_bbox = clamp_bbox(sec_bbox[0], sec_bbox[1], sec_bbox[2], sec_bbox[3], W, H)

    if sec_bbox is None:
        raise HTTPException(status_code=400, detail="Provide a profile or section multipliers")

    crop = crop_to_bbox(img_bgr, tuple(sec_bbox))
    png = cv2_to_png_bytes(crop)
    return StreamingResponse(iter([png]), media_type="image/png")

@app.post("/cut-section-bulk")
async def cut_section_bulk(
    images: List[UploadFile] = File(..., description="Multiple scanned images"),
    template: Optional[UploadFile] = File(None, description="Logo template image (optional if default exists)"),
    method: str = Form("auto"),
    profile: Optional[str] = Form(None),
    # explicit params fallback
    section_left_mul: Optional[float] = Form(None),
    section_top_mul: Optional[float] = Form(None),
    section_right_mul: Optional[float] = Form(None),
    section_bottom_mul: Optional[float] = Form(None),
    section_width_mul: Optional[float] = Form(None),
    section_height_mul: Optional[float] = Form(None),
):
    # Read template once
    tmpl_bytes = _get_template_bytes(template)
    tmpl_bgr = bytes_to_cv2_image(tmpl_bytes)

    mem = io.BytesIO()
    manifest = []

    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for i, uf in enumerate(images):
            name = os.path.splitext(os.path.basename(uf.filename or f"image_{i}.png"))[0]
            try:
                img_bytes = await uf.read()
                img_bgr = bytes_to_cv2_image(img_bytes)

                res = detect_logo(img_bgr, tmpl_bgr, method=method)
                if res is None:
                    manifest.append({"file": uf.filename, "status": "logo_not_found"})
                    continue

                # compute section bbox
                sec_bbox = None
                if profile:
                    prof = get_profile(profile)
                    if prof is None:
                        manifest.append({"file": uf.filename, "status": "profile_not_found", "profile": profile})
                        continue
                    sec_bbox = prof.compute_bbox(img_bgr.shape, tuple(res["bbox"]))
                elif section_left_mul is not None and section_top_mul is not None:
                    if section_right_mul is not None and section_bottom_mul is not None:
                        sec_bbox = rect_from_logo_relative(
                            img_bgr.shape, tuple(res["bbox"]),
                            section_left_mul, section_top_mul, section_right_mul, section_bottom_mul,
                        )
                    elif section_width_mul is not None and section_height_mul is not None:
                        x, y, w, h = tuple(res["bbox"])
                        x1 = int(round(x + section_left_mul * w))
                        y1 = int(round(y + section_top_mul * h))
                        x2 = int(round(x1 + section_width_mul * w))
                        y2 = int(round(y1 + section_height_mul * h))
                        sec_bbox = [min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)]
                        H, W = img_bgr.shape[:2]
                        sec_bbox = clamp_bbox(sec_bbox[0], sec_bbox[1], sec_bbox[2], sec_bbox[3], W, H)

                if sec_bbox is None:
                    manifest.append({"file": uf.filename, "status": "no_section_params"})
                    continue

                crop = crop_to_bbox(img_bgr, tuple(sec_bbox))
                png = cv2_to_png_bytes(crop)
                zf.writestr(f"{name}_section.png", png)
                manifest.append({
                    "file": uf.filename,
                    "status": "ok",
                    "logo_bbox": res.get("bbox"),
                    "section_bbox": [int(x) for x in sec_bbox],
                    "method": res.get("method"),
                    "confidence": res.get("confidence"),
                })
            except Exception as e:
                manifest.append({"file": getattr(uf, 'filename', None), "status": "error", "error": str(e)})
        # add manifest.json
        zf.writestr("manifest.json", json.dumps(manifest, indent=2))

    mem.seek(0)
    headers = {"Content-Disposition": "attachment; filename=sections.zip"}
    return StreamingResponse(mem, media_type="application/zip", headers=headers)
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, reload=True)
