# Logo Locator API

Detect your logo in scanned forms and return the annotated image (red rectangle) or the bounding box as JSON.

## Stack
- FastAPI
- OpenCV (ORB + multi-scale template matching)

## Setup (Windows friendly)
1. Create and activate a virtual environment (PowerShell):
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
2. Install dependencies:
   ```powershell
   pip install -r requirements.txt
   ```
3. Place your logo template at `app/assets/logo.png` (or pass it per-request).

## Run the API
```powershell
python -m app.main
# or
uvicorn app.main:app --reload --port 8000
```

Open https://lancasterfarmingapis.onrender.com/docs for Swagger UI.

Production base URL: https://lancasterfarmingapis.onrender.com

## Endpoints
- `POST /detect` -> JSON with `bbox [x,y,w,h]`, `confidence`, `method`.
- `POST /annotate` -> Returns image/png with red rectangle around detected logo.
- `POST /cut-section` -> Returns image/png of the cropped section only (green box area).
- Profiles management: `GET/PUT/DELETE /profiles/{name}`, `GET /profiles`

Both accept multipart form-data:
- `image`: the scanned form image (required)
- `template`: the logo image (optional if default is present)
- `method`: `auto` | `orb` | `template` (default: `auto`)
- `thickness` (only for `/annotate`)

## Example (PowerShell)
```powershell
# Detect
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/detect -Method Post -Form @{ 
    image=Get-Item .\samples\form.png; 
    template=Get-Item .\app\assets\logo.png; 
    method='auto' 
} | Select-Object -ExpandProperty Content | Set-Content detect.json

# Annotate
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/annotate -Method Post -Form @{ 
    image=Get-Item .\samples\form.png; 
    template=Get-Item .\app\assets\logo.png; 
    method='auto'; thickness=4 
} -OutFile annotated.png
```

## CLI (batch annotate)
```powershell
python cli.py .\samples --template .\app\assets\logo.png --out out
```

## Notes
- ORB feature matching gives scale/rotation robustness and usually finds the logo on scans.
- If features are weak, we fall back to multi-scale template matching.
- You can tune or restrict the search by cropping the template tightly around the logo.

## Profiles and Section Cropping
You can define a named profile that describes the section relative to the detected logo using normalized multipliers. Two modes are supported:
- `edge`: provide `left_mul`, `top_mul`, `right_mul`, `bottom_mul` (all multiples of logo width/height). Negative values move left/up.
- `size`: provide `left_mul`, `top_mul`, `width_mul`, `height_mul`.

### Create/Update a profile (edge mode)
```powershell
$body = @{ 
  name = 'form_a'; mode = 'edge';
  left_mul = -2; top_mul = -1; right_mul = 12; bottom_mul = 6;
  section_thickness = 3
} | ConvertTo-Json

Invoke-RestMethod -Uri https://lancasterfarmingapis.onrender.com/profiles/form_a -Method Put -ContentType 'application/json' -Body $body
```

### Annotate using a profile
```powershell
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/annotate -Method Post -Form @{
  image=Get-Item .\samples\form.png; template=Get-Item .\app\assets\logo.png;
  profile='form_a'
} -OutFile annotated.png
```

### Cut the section only
```powershell
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/cut-section -Method Post -Form @{
  image=Get-Item .\samples\form.png; template=Get-Item .\app\assets\logo.png;
  profile='form_a'
} -OutFile section.png
```

## API Reference

### POST /detect
- **Description**: Detect the logo and return its bounding box and metadata.
- **Consumes**: multipart/form-data
- **Form fields**:
  - `image` (file, required)
  - `template` (file, optional if default exists)
  - `method` (string; `auto` | `orb` | `template`; default `auto`)
- **Returns**: `application/json`

Example (PowerShell):
```powershell
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/detect -Method Post -Form @{
  image=Get-Item .\samples\form.png;
  template=Get-Item .\app\assets\logo.png;
  method='auto'
} | Select-Object -ExpandProperty Content | Set-Content detect.json
```

Sample JSON:
```json
{
  "width": 2550,
  "height": 3300,
  "method": "orb",
  "confidence": 0.62,
  "bbox": [1820, 2740, 400, 120],
  "polygon": [[1824,2741],[2220,2742],[2222,2860],[1821,2856]]
}
```

### POST /annotate
- **Description**: Returns the original image with a red rectangle on the logo, and optionally a green rectangle for a section relative to the logo.
- **Consumes**: multipart/form-data
- **Form fields**:
  - `image` (file, required)
  - `template` (file, optional)
  - `method` (string)
  - `thickness` (int; red logo box thickness)
  - `profile` (string; optional saved profile name)
  - Section via multipliers (if not using `profile`):
    - Edge mode: `section_left_mul`, `section_top_mul`, `section_right_mul`, `section_bottom_mul`
    - Size mode: `section_left_mul`, `section_top_mul`, `section_width_mul`, `section_height_mul`
- **Returns**: `image/png`

Example:
```powershell
Invoke-WebRequest -Uri http://localhost:8000/annotate -Method Post -Form @{
  image=Get-Item .\samples\form.png;
  template=Get-Item .\app\assets\logo.png;
  profile='form_a'; thickness=4
} -OutFile annotated.png
```

### POST /cut-section
- **Description**: Returns only the cropped section as PNG. Section is computed via `profile` or explicit multipliers.
- **Consumes**: multipart/form-data
- **Form fields**: same as `/annotate` (no thickness fields used)
- **Returns**: `image/png`

Example:
```powershell
Invoke-WebRequest -Uri http://localhost:8000/cut-section -Method Post -Form @{
  image=Get-Item .\samples\form.png; template=Get-Item .\app\assets\logo.png; profile='form_a'
} -OutFile section.png
```

### POST /cut-section-bulk
- **Description**: Process multiple images, return a ZIP with each cropped section and a manifest.
- **Consumes**: multipart/form-data
- **Form fields**:
  - `images` (file[]; multiple files required)
  - `template` (file, optional)
  - `method` (string)
  - `profile` (string) or section multipliers (same as `/annotate`)
- **Returns**: `application/zip` with files:
  - `<original>_section.png`
  - `manifest.json`

Example:
```powershell
Invoke-WebRequest -Uri https://lancasterfarmingapis.onrender.com/cut-section-bulk -Method Post -Form @{
  "images" = (Get-Item .\samples\*.png);
  template = Get-Item .\app\assets\logo.png;
  profile = 'form_a'
} -OutFile sections.zip
```

Sample `manifest.json` entry:
```json
[
  {
    "file": "form_001.png",
    "status": "ok",
    "logo_bbox": [1820, 2740, 400, 120],
    "section_bbox": [1600, 2000, 1500, 900],
    "method": "orb",
    "confidence": 0.58
  },
  {
    "file": "form_002.png",
    "status": "logo_not_found"
  }
]
```

### Profiles
- `GET https://lancasterfarmingapis.onrender.com/profiles` → JSON map of saved profiles.
- `GET https://lancasterfarmingapis.onrender.com/profiles/{name}` → profile JSON.
- `PUT /profiles/{name}` → create/update. Body JSON (edge example):
```json
{
  "name": "form_a",
  "mode": "edge",
  "left_mul": -2,
  "top_mul": -1,
  "right_mul": 12,
  "bottom_mul": 6,
  "section_thickness": 3
}
```
- `DELETE /profiles/{name}` → removes a profile.
