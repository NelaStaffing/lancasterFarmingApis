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

Open http://localhost:8000/docs for Swagger UI.

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
Invoke-WebRequest -Uri http://localhost:8000/detect -Method Post -Form @{ 
    image=Get-Item .\samples\form.png; 
    template=Get-Item .\app\assets\logo.png; 
    method='auto' 
} | Select-Object -ExpandProperty Content | Set-Content detect.json

# Annotate
Invoke-WebRequest -Uri http://localhost:8000/annotate -Method Post -Form @{ 
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

Invoke-RestMethod -Uri http://localhost:8000/profiles/form_a -Method Put -ContentType 'application/json' -Body $body
```

### Annotate using a profile
```powershell
Invoke-WebRequest -Uri http://localhost:8000/annotate -Method Post -Form @{
  image=Get-Item .\samples\form.png; template=Get-Item .\app\assets\logo.png;
  profile='form_a'
} -OutFile annotated.png
```

### Cut the section only
```powershell
Invoke-WebRequest -Uri http://localhost:8000/cut-section -Method Post -Form @{
  image=Get-Item .\samples\form.png; template=Get-Item .\app\assets\logo.png;
  profile='form_a'
} -OutFile section.png
```
