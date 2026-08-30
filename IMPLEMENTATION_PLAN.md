# Implementation Plan — Contour-Based Pond Catchment Analysis API

## 1. Overview & Goals

**Course/Context:** System Design mid-sem assignment.

**Objective:** Build a backend API that accepts a contour map (KML/KMZ), analyzes
terrain, identifies a suitable pond location, and returns the corresponding
catchment area as structured JSON.

**Hard constraints:**
- No hardcoded coordinates, elevations, or results tied to the sample file
  (`contours_1m.kml`). Every number in the output must be derived at request time.
- Must generalize to other contour maps in phase 2 (different extents, elevation
  ranges, contour intervals, coordinate systems).
- Must run on a target deployment box with **512MB RAM / 1 vCPU / 1.5GB storage**.

**Reference sample file characteristics** (used for design/testing, never hardcoded
into logic):
- Extent: ~3.2km × 2.6km
- Elevation range: 267m–298m, 1m contour interval
- 2711 contour polylines, ~160k coordinate points, WGS84 lon/lat

**Tech stack:** FastAPI + Uvicorn, numpy/scipy for interpolation and terrain
analysis, shapely for geometry, pyproj for projection, lxml for KML parsing.
Deliberately avoids GDAL/rasterio/richdem/pysheds — too heavy for the 1.5GB
storage budget.

## 2. Architecture

Layered pipeline, each layer an independent, swappable module behind a clear
interface — this is what makes phase 2 generalization possible without touching
the API layer:

```
Upload (KML/KMZ)
      |
      v
[1] Parser layer        -> ContourDataset (elevation, list of polylines in lon/lat)
      |
      v
[2] Projection layer     -> reproject lon/lat to local UTM meters (pyproj)
      |
      v
[3] DEM builder layer    -> rasterize contours + scipy.interpolate.griddata
      |                      => elevation grid (numpy array), config: resolution_m
      v
[4] Terrain analysis     -> depression fill, D8 flow direction, flow accumulation
      |
      v
[5] Pond site selector   -> heuristic scoring over candidate cells
      |
      v
[6] Catchment delineator -> watershed trace from chosen outlet -> boundary polygon
      |
      v
[7] Response builder     -> JSON (pond site, catchment polygon, area, stats)
```

Each layer takes/returns plain data structures (numpy arrays, dataclasses,
shapely geometries) — no layer knows about FastAPI or file I/O, so they're
independently unit-testable and reusable if the interface (e.g. a REST route vs
a CLI) changes later.

## 3. Resource Constraints & Design Decisions

Target box: **512MB RAM, 1 vCPU, 1.5GB storage.** This drives several choices:

| Decision | Reasoning |
|---|---|
| `resolution_m` is a required config knob, not fixed | Sample area at 1m resolution = ~8.6M grid cells — too much for 512MB with flow-accumulation. Default 10m (~86k cells) on constrained deploy; laptop dev can use 2–5m. |
| Auto-scale resolution by extent | Guard rail: if `(width_m / resolution_m) * (height_m / resolution_m)` exceeds a cell-count ceiling, auto-coarsen resolution and report the adjustment in the response. Prevents phase-2 maps (potentially larger) from OOM-killing the process. |
| No GDAL/rasterio/richdem/pysheds | These pull in large system libraries (100s of MB) that would consume a big share of the 1.5GB disk. Custom pure-numpy D8 flow direction/accumulation and priority-flood fill are lightweight and sufficient at this cell-count scale. |
| No Docker on the target box | A Docker image + engine overhead competes with the 1.5GB disk budget. Deploy as a plain venv + systemd service instead. Docker is fine for local dev if convenient, just not required for the deploy step. |
| Single uvicorn worker, no gunicorn multi-worker | Only 1 vCPU — multiple workers would just context-switch, not add throughput. |
| Streamed file upload handling | Even though the sample file is small, phase-2 files are unbounded — write upload to a temp file on disk rather than buffering fully in memory. |
| Swap file on the target box | 512MB is tight; a 512MB–1GB swap file is a cheap safety net against transient spikes (recommended as a deploy-step task, not app-level). |

## 4. Phase-by-Phase Module Breakdown

Each row below is one git commit (or a small tight sequence of commits) once
implementation starts.

1. **Project scaffold** — FastAPI app skeleton, `requirements.txt`, folder
   layout (`app/parser`, `app/dem`, `app/terrain`, `app/pond`, `app/api`,
   `tests/`), `.gitignore`, README stub.
2. **KML/KMZ parser** (`app/parser/`) — handles KMZ unzip, parses with `lxml`
   using namespace-agnostic XPath (robust to nonstandard attributes like the
   `py:pytype` seen in the sample file). Outputs a generic `ContourDataset`
   (list of `(elevation: float, points: list[(lon, lat)])`). Unit test against
   the sample file: assert elevation range, polyline count, no exceptions.
3. **Projection + DEM builder** (`app/dem/`) — reprojects lon/lat to local UTM
   via `pyproj`, rasterizes contour lines onto a grid, fills via
   `scipy.interpolate.griddata`. `resolution_m` and the auto-coarsening guard
   rail live here.
4. **Terrain analysis** (`app/terrain/`) — priority-flood depression fill, D8
   flow direction, flow accumulation. Pure numpy, unit-tested on small
   synthetic grids (e.g. a synthetic bowl/ridge) before running on the real DEM.
5. **Pond site selection + catchment delineation** (`app/pond/`) — scoring
   heuristic (high flow accumulation + local depression/flat + not on grid
   boundary, thresholds configurable) to pick an outlet cell; watershed trace
   upstream from that outlet; boundary polygon via `shapely`.
6. **API wiring** (`app/api/`) — `POST /analyzeContour` route: file upload
   handling (streamed to temp file), query params (`resolution_m`,
   `min_catchment_area_m2`), Pydantic response schema, `GET /health`. Central
   error handling for invalid files / no valid pond found.
7. **Local integration testing** — run full pipeline against
   `contours_1m.kml`, validate output sanity (catchment area within plausible
   bounds, polygon actually closes, pond site inside the DEM extent), exercise
   edge cases (corrupt file, unsupported format, degenerate/flat terrain).
8. **Deployment** — systemd unit file, deploy script, swap-file setup note,
   optional Nginx reverse proxy config, remote smoke test.
9. **Report & docs** — README architecture section, API docs (FastAPI
   auto-generates OpenAPI/Swagger at `/docs`), demo walkthrough with actual
   output from the sample file, GitHub repo link.

## 5. API Design

```
POST /analyzeContour
Content-Type: multipart/form-data

Form fields:
  file                    required, .kml or .kmz
  resolution_m            optional, float, default 10.0
  min_catchment_area_m2   optional, float, default 500.0

Response 200 (application/json):
{
  "contour_interval_m": 1.0,
  "elevation_range_m": [267.0, 298.0],
  "grid_resolution_m": 10.0,
  "resolution_auto_adjusted": false,
  "pond_site": {
    "lat": 21.2521,
    "lon": 81.2934,
    "elevation_m": 274.0
  },
  "catchment": {
    "area_m2": 184500.2,
    "area_hectares": 18.45,
    "mean_slope_pct": 6.7,
    "boundary_geojson": { "type": "Polygon", "coordinates": [[[...]]] }
  },
  "processing_time_ms": 842
}

Error responses:
  400 — invalid/corrupt file, unsupported format
  422 — no valid pond site found (e.g. perfectly flat or invalid terrain)
  500 — unexpected processing failure

GET /health
  -> { "status": "ok" }
```

All numeric outputs above are illustrative shape only — actual values are
computed from whatever file is uploaded, never hardcoded.

## 6. Local Development & Testing Workflow

1. Build and run entirely on laptop first: `venv`, `pip install -r
   requirements.txt`, `uvicorn app.main:app --reload`.
2. Unit tests per module (parser, DEM builder, terrain analysis, pond
   selector) with `pytest`, using both the real sample KML and small synthetic
   grids for the terrain-analysis math (synthetic cases are easier to assert
   exact expected behavior on, e.g. a synthetic single-bowl DEM should produce
   one clear outlet).
3. Integration test: full `POST /analyzeContour` call against
   `contours_1m.kml` via `TestClient` (or `curl`), assert response shape and
   sane value ranges — not exact values, since the algorithm/thresholds may
   evolve.
4. Only once local run + tests pass do we move to deployment — never debug
   the pipeline for the first time on the constrained remote box.

## 7. Deployment Workflow (Remote Constrained Box)

1. `git pull` (or `scp`) the repo onto the 512MB/1vCPU/1.5GB machine.
2. Create a fresh venv, install pinned `requirements.txt` — confirm final
   installed size stays well under the 1.5GB disk budget.
3. Set up a swap file (512MB–1GB) as a safety margin.
4. Configure environment for constrained defaults (e.g. `resolution_m=10`,
   cell-count ceiling for the auto-coarsening guard rail).
5. Run under `systemd` with a single uvicorn worker, `Restart=on-failure`.
6. (Optional) Nginx as a reverse proxy in front of uvicorn.
7. Smoke test: re-run the same `contours_1m.kml` request against the deployed
   URL and diff the response against the local run's output.
8. Record the working API URL in the report.

## 8. Git Commit Strategy

One commit (or a tight, reviewable sequence) per subsection above — never one
giant commit at the end. Convention: `<type>: <what>`, e.g.

```
feat: add KML/KMZ parser module
test: add parser unit tests against sample contour file
feat: add DEM builder with resolution auto-scaling guard rail
feat: add priority-flood depression fill
feat: add D8 flow direction and accumulation
feat: add pond site scoring heuristic
feat: add watershed delineation and boundary polygon builder
feat: wire analyzeContour API route
test: add integration test against sample KML
chore: add systemd unit and deploy script
docs: add report and API documentation
```

This mirrors how this plan doc itself was committed section-by-section, and
gives the evaluator a clear history of how the system was built up.

## 9. Report Deliverable Checklist

- [ ] GitHub repo link
- [ ] Working API route URL (remote deployment)
- [ ] Catchment estimation approach — summary of Sections 1–2 above
- [ ] Demonstration using `contours_1m.kml` (request + actual response)
- [ ] API documentation (link to `/docs` Swagger UI + this plan's Section 5)
