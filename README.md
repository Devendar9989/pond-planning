# Contour-Based Pond Catchment Analysis API

A high-performance, memory-efficient backend service built with **FastAPI** to analyze contour maps (KML/KMZ), reconstruct Digital Elevation Models (DEMs), perform hydrological terrain analysis, identify optimal farm pond locations, and delineate upstream catchment boundaries as GeoJSON polygons.

Designed and engineered to run reliably within severe hardware constraints: **512MB RAM, 1 vCPU, and 1.5GB disk storage**.

---

## 1. System Architecture

```
[Client / GIS Tool]
        │  POST /analyzeContour (multipart/form-data: .kml/.kmz)
        ▼
[1] Fast Streaming Upload Handler
        │  Streams upload chunks to disk tempfile (RAM < 25MB)
        ▼
[2] Namespace-Agnostic KML/KMZ Parser (`app/parser/`)
        │  lxml XPath parsing, handles KMZ zip archives & custom attributes
        ▼
[3] Metric Projection & DEM Builder (`app/dem/`)
        │  Auto-determines local UTM zone (pyproj) & performs SciPy grid interpolation
        │  *Auto-coarsening guard rail prevents OOM if cell count > 150k*
        ▼
[4] Pure-NumPy Hydrology Engine (`app/terrain/`)
        ├── Priority-Flood depression filling (heapq + NumPy)
        ├── 2nd-order terrain slope & aspect gradient
        ├── D8 steepest descent flow direction
        └── O(N) Topological in-degree flow accumulation
        ▼
[5] Multi-Criteria Pond Siting & Catchment Delineation (`app/pond/`)
        ├── Heuristic score: High accumulation (70%) + Flatness/Low slope (30%)
        ├── Reverse-D8 upstream watershed traversal (BFS)
        └── Vector boundary polygon generation (Shapely) -> WGS84 GeoJSON
        ▼
[Response Payload]
        Structured JSON with pond location, catchment area, slope, and GeoJSON boundary.
```

---

## 2. Key Engineering & Resource Decisions

| Design Decision | Rationale |
|---|---|
| **Pure NumPy Hydrology Engine** | Avoids heavy C/C++ GIS bindings (GDAL, rasterio, richdem, pysheds) which would consume hundreds of megabytes on a 1.5GB disk. |
| **Auto-Coarsening Guard Rail** | Prevents Out-Of-Memory (OOM) failures on large map extents by dynamically adjusting `resolution_m` if grid size exceeds `MAX_GRID_CELLS` (150,000 cells). |
| **Topological In-Degree Flow Accumulation** | Traverses drainage networks in $O(N)$ operations starting at ridge lines without recursion or stack-overflow risk. |
| **Disk-Streamed Uploads** | Large KML/KMZ files are written directly to temporary files rather than buffered entirely in memory. |
| **Zero Hardcoding** | Every single coordinate, elevation, contour interval, and watershed boundary is computed dynamically at request time. |

---

## 3. API Specification

### `GET /health`
Verifies server health and readiness.

**Response (200 OK):**
```json
{
  "status": "ok"
}
```

---

### `POST /analyzeContour`
Uploads a contour map, executes hydrological modeling, and returns the optimal pond location and catchment.

**Request:** `multipart/form-data`
- `contour_map` *(required)*: `.kml` or `.kmz` contour map file (fallback parameter name: `file`).
- `resolution_m` *(optional, default: `10.0`)*: Target grid resolution in meters.
- `min_catchment_area_m2` *(optional, default: `500.0`)*: Minimum upstream catchment area threshold.

**Sample Request (`curl`):**
```bash
curl -X POST "http://10.1.75.51:3241/analyzeContour" \
  -F "contour_map=@contours_1m.kml" \
  -F "resolution_m=10.0" \
  -F "min_catchment_area_m2=500.0"
```

**Sample Response (200 OK):**
```json
{
  "contour_interval_m": 1.0,
  "elevation_range_m": [267.0, 298.0],
  "total_contour_lines": 2710,
  "grid_resolution_m": 10.0,
  "grid_shape": [264, 326],
  "resolution_auto_adjusted": false,
  "pond_site": {
    "lat": 21.244413,
    "lon": 81.291006,
    "elevation_m": 275.0,
    "flow_accumulation_cells": 166
  },
  "catchment": {
    "area_m2": 16600.0,
    "area_hectares": 1.66,
    "mean_slope_pct": 3.58,
    "max_slope_pct": 10.93,
    "min_elevation_m": 275.0,
    "max_elevation_m": 281.0,
    "relief_m": 6.0,
    "watershed_cell_count": 166,
    "boundary_geojson": {
      "type": "Polygon",
      "coordinates": [
        [
          [81.290476, 21.244549],
          [81.290477, 21.245092],
          [81.290573, 21.245091],
          [81.290476, 21.244549]
        ]
      ]
    }
  },
  "processing_time_ms": 842
}
```

**Error Responses:**
- `400 Bad Request`: Invalid file format, corrupt XML, or invalid parameters.
- `422 Unprocessable Entity`: No valid pond site satisfies the minimum catchment criteria.
- `500 Internal Server Error`: Unexpected terrain calculation failure.

Interactive Swagger documentation is automatically available at **`http://localhost:8000/docs`**.

---

## 4. Local Development & Testing

### Installation
```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt
```

### Running the Server
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Running Tests
Execute the comprehensive test suite with `pytest`:
```bash
pytest -v
```

---

## 5. Remote Deployment (512MB RAM Target Box)

1. Clone or transfer the codebase to the server:
   ```bash
   git clone <repo_url> /opt/pond-api
   cd /opt/pond-api
   ```
2. Run the automated deployment script:
   ```bash
   chmod +x deploy/deploy.sh
   ./deploy/deploy.sh
   ```
   *The script automatically creates a 1GB swapfile for safety, builds the virtual environment with `--no-cache-dir`, and starts the systemd service (`pond-api.service`).*
