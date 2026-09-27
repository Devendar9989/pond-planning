# Implementation Plan — Contour-Based Pond Catchment Analysis API (VIVA & Demo)

## 1. System Overview & Objectives

**Course/Context:** System Design VIVA & Demo.

**Project Title:** **PondPlan AI** — Autonomous Contour-Based Farm Pond Siting, Catchment Delineation, and Water Harvest Volume Estimation.

**Objective:** Deliver an end-to-end production geospatial platform comprising an asynchronous Python backend API and a responsive interactive Web Front-End that accepts topographic contour survey maps (KML/KMZ), reconstructs metric Digital Elevation Models (DEMs), models terrain surface hydrology, allows interactive land area selection on a map, identifies optimal farm pond outlet sites, estimates expected harvestable runoff water volume, and delineates upstream catchment boundaries as topologically valid GeoJSON polygons.

---

## 2. VIVA & Demo Required Deliverables

| Required Submission | Location & Link | Status |
|---|---|:---:|
| **1. Final Working Front-End URL** | **`http://10.1.75.51:3241/`** *(and port `3000`: `http://10.1.75.51:3000/`)* | ✅ **Active** |
| **2. GitHub Repository URL** | **`https://github.com/Devendar9989/pond-planning.git`** | ✅ **Committed** |
| **3. Final Report (Overleaf Template)** | [`REPORT_OVERLEAF.tex`](file:///c:/Users/PC/Downloads/pond%20planning/REPORT_OVERLEAF.tex) (matches [Overleaf Template](https://www.overleaf.com/read/pzfvwbrjswhz#d2b10f)) | ✅ **Ready (Max 10 pages)** |
| **4. 5-Min Public YouTube Demo Video Script** | [`YOUTUBE_DEMO_SCRIPT.md`](file:///c:/Users/PC/Downloads/pond%20planning/YOUTUBE_DEMO_SCRIPT.md) | ✅ **Ready** |
| **5. Live API Analysis Endpoint** | `POST http://10.1.75.51:3241/analyzeContour` | ✅ **Active** |
| **6. Interactive Swagger API Docs** | `http://10.1.75.51:3241/docs` | ✅ **Active** |
| **7. Remote Deployment Server** | `ssh -p 2241 student@10.1.75.51` (Path: `/home/student/pond_panning`) | ✅ **Deployed** |

---

## 3. End-to-End System Architecture

The system employs a layered, stateless architecture powered by FastAPI, vectorized NumPy/SciPy computing engines, and a responsive Leaflet Single Page Application:

```
+-----------------------------------------------------------------------------------------------+
|                                  INTERACTIVE WEB FRONT-END                                    |
|   Leaflet Map (OSM/Satellite/Topo) | Land Area AOI Draw Tools | Real-Time Volume Dashboard    |
+-----------------------------------------------------------------------------------------------+
                                               |
                                               | HTTP POST (multipart/form-data)
                                               | - contour_map: .kml / .kmz file
                                               | - resolution_m: 10.0
                                               | - min_catchment_area_m2: 500.0
                                               | - rainfall_mm: 1000.0
                                               | - runoff_coefficient: 0.35
                                               | - selected_bounds: [min_lon, min_lat, max_lon, max_lat]
                                               v
+-----------------------------------------------------------------------------------------------+
|                                    FASTAPI SERVICE LAYER                                      |
|   /analyzeContour (primary: contour_map, fallback: file) | /health | Static UI Mount (/)      |
+-----------------------------------------------------------------------------------------------+
                                               |
        +--------------------------------------+--------------------------------------+
        |                                      |                                      |
        v                                      v                                      v
+-----------------------+          +-----------------------+          +-----------------------+
|  [1] KML/KMZ Parser   |          |  [2] Metric Projection|          |  [3] Hydrology Engine |
|  - Namespace-agnostic |--------->|  - Auto UTM zone EPSG |--------->|  - Priority-Flood Fill|
|  - In-memory KMZ zip  |          |  - Linear Barycentric |          |  - 2nd-Order Slope %  |
|  - Disk-streamed I/O  |          |  - Memory Guard Rail  |          |  - D8 Steepest Routing|
+-----------------------+          +-----------------------+          |  - O(N) In-Degree DAG |
                                                                      +-----------------------+
                                                                                  |
                                                                                  v
+-----------------------------------------------------------------------------------------------+
|                    [4] MULTI-CRITERIA POND SITING & CATCHMENT DELINEATION                     |
|  - Land Area AOI Filtering: Restricts candidate cells inside user's drawn boundary            |
|  - Multi-Criteria Siting Heuristic: Accumulation (70%) + Slope <= 8% (30%) + Sink Depth       |
|  - Reverse-D8 BFS Watershed Tracing: Traverses upstream contributing area                     |
|  - Vector Boundary Polygonization: Shapely unary_union -> WGS84 GeoJSON                       |
|  - Hydrological Water Volume Estimation: Rational Runoff Method (m³, Liters, Million Liters)  |
+-----------------------------------------------------------------------------------------------+
                                               |
                                               v
+-----------------------------------------------------------------------------------------------+
|                                   STRUCTURED JSON RESPONSE                                    |
|   Pond Lat/Lon/Elev | Catchment Area (ha) | Volume (m³) | Overlaid GeoJSON Polygon Boundary   |
+-----------------------------------------------------------------------------------------------+
```

---

## 4. Expected System Requirements & Feature Implementation

### 4.1 Fully Working Front-End Single Page Application
* **Hosted At:** `http://10.1.75.51:3241/`
* **File:** [`app/static/index.html`](file:///c:/Users/PC/Downloads/pond%20planning/app/static/index.html)
* **Map Engine:** Leaflet 1.9.4 with layer switcher (Esri World Imagery Satellite, OpenStreetMap, OpenTopoMap).
* **1-Click Preloaded Survey:** Dedicated "Load Survey Map" button preloads `contours_1m.kml` for instant live demos, with a drag-and-drop file uploader for custom KML/KMZ files.

### 4.2 Interactive Land Area (AOI) Selection on Map
* **Drawing Tools:** Interactive **"Draw Rectangle"** and **"Draw Polygon"** tools powered by Leaflet Draw.
* **Dynamic AOI Extraction:** As the user draws, coordinates ($[\text{min\_lon}, \text{min\_lat}, \text{max\_lon}, \text{max\_lat}]$) are extracted and passed to the backend.
* **Constrained Pond Siting:** The backend reprojects the bounding box to UTM, builds a 2D boolean raster mask, and restricts candidate pond siting strictly inside the user's selected parcel.

### 4.3 Suggested Pond Location
* **Heuristic Formulation:**
  $$\text{Score}(c) = 0.70 \cdot \frac{\ln(1 + A_c)}{\max \ln(1 + A)} + 0.30 \cdot f(\text{Slope}_c) + \text{DepressionDepth}_c$$
  where $f(\text{Slope})$ assigns full weight to slopes $\le 8\%$ and penalizes slopes $>8\%$.
* **Map Overlay:** Marked with a pulsating animated water drop icon. Clicking opens a rich popup with elevation, coordinates, contributing cells, and water yield.

### 4.4 Catchment Area Delineation
* **Traversed Upstream:** Reverse-D8 Breadth-First Search (BFS) traces all upstream contributing cells.
* **Vector Polygonization:** Raster cell bounding boxes are dissolved using Shapely `unary_union`, topologically simplified with half-pixel tolerance, and converted to WGS84 GeoJSON.
* **Map Overlay:** Rendered as a distinct, semi-transparent cyan shaded polygon.

### 4.5 Expected Water Volume Collection Modeling
* **Hydrological Formulation (Rational Runoff Method):**
  $$V_{\text{annual}} (m^3) = \text{Catchment Area } (m^2) \times \left(\frac{\text{Rainfall } (mm)}{1000}\right) \times C$$
  $$V_{\text{Liters}} = V_{\text{annual}} \times 1000, \quad V_{\text{ML}} = \frac{V_{\text{annual}}}{1000}$$
* **Interactive Controls:**
  * **Rainfall Slider:** $200\text{mm}$ (Arid) to $2500\text{mm}$ (Heavy Monsoon), default $1000\text{mm}$.
  * **Runoff Coefficient ($C$):** Sandy soil ($0.20$), Agricultural loam ($0.35$), Clay soil ($0.50$), Rocky terrain ($0.70$).
* **Equivalence Metrics:** Real-time translation to equivalent Olympic swimming pools ($\approx 2,500\text{ m}^3/\text{pool}$) and days of 5-acre farm irrigation.

---

## 5. Demonstration on Reference Map (`contours_1m.kml`)

Topographic analysis of the provided $3.2\text{km} \times 2.6\text{km}$ survey map in Chhattisgarh, India (2,710 contour lines):

| Hydrological Metric | Computed Value & Agricultural Significance |
|---|---|
| **Detected Contour Interval** | $1.0\text{ m}$ (dynamically calculated) |
| **Elevation Range** | $267.0\text{ m} - 298.0\text{ m}$ ($31.0\text{ m}$ total vertical relief) |
| **Optimal Pond Location** | Latitude $\mathbf{21.251833^\circ\text{N}}$, Longitude $\mathbf{81.296571^\circ\text{E}}$ |
| **Pond Surface Elevation** | $\mathbf{270.0\text{ m}}$ AMSL (natural drainage outlet) |
| **Flow Accumulation** | $310$ raster cells ($31,000\text{ m}^2$ direct channel drainage) |
| **Contributing Catchment Area** | $\mathbf{44,300.0\text{ m}^2}$ ($\mathbf{4.43\text{ Hectares}}$, $443$ raster cells) |
| **Mean Catchment Slope** | $4.80\%$ (optimal for stable runoff collection) |
| **Basin Relief** | $23.0\text{ m}$ ($270.0\text{ m} \rightarrow 293.0\text{ m}$) |
| **Expected Harvestable Water Volume** | $\mathbf{15,505.0\text{ m}^3}$ ($\mathbf{15.51\text{ Million Liters / ML}}$ at $1000\text{mm}$, $C=0.35$) |
| **Agricultural Equivalence** | $\approx \mathbf{6.2\text{ Olympic Swimming Pools}}$ ($\approx \mathbf{31\text{ days of 5-acre irrigation}}$) |
| **End-to-End Processing Time** | $\approx 2,446\text{ ms}$ |

---

## 6. Multi-System Scaling, Stress, and Resource Constraints

### 6.1 Hardware Budget Compliance (512MB RAM / 1 vCPU / 1.5GB Disk)
* **Pure-NumPy Engine:** Avoided GDAL, rasterio, richdem, and pysheds (which exceed hundreds of megabytes).
* **Auto-Coarsening Guard Rail:** If grid size exceeds $150,000$ cells on large map extents, resolution auto-adjusts dynamically:
  $$\Delta x_{\text{adjusted}} = \sqrt{\frac{W_{\text{meters}} \times H_{\text{meters}}}{150,000}}$$
* **Disk-Streamed Uploads:** Streamed in 64KB chunks to temporary disk files, preventing RAM exhaustion.

### 6.2 Scaling Across 4 Student Systems
* **Stateless REST Services:** The API maintains zero in-memory session state.
* **Distributed Worker Nodes:** Can run concurrently across the four student systems (`10.1.75.51:3241`, `172.17.0.43:3242`, `172.17.0.44:3243`, `172.17.0.45:3244`) behind a round-robin / least-connections reverse-proxy load balancer.

---

## 7. Verification & Testing Suite

* **Automated Test Suite:** 23 tests in `tests/` covering API validation, KML parsing, UTM projection, Priority-Flood filling, D8 routing, pond siting, and synthetic terrain scenarios (V-valley, bowl sink, KMZ archive, Australian southern hemisphere, area filters, dual ridge divides).
* **Test Command:**
  ```bash
  pytest -v
  ```
  *Result:* **23 passed in 51.99s**.

---

## 8. Report & Presentation Deliverables

1. **Overleaf LaTeX Report Source:**
   * File: [`REPORT_OVERLEAF.tex`](file:///c:/Users/PC/Downloads/pond%20planning/REPORT_OVERLEAF.tex)
   * Template: [https://www.overleaf.com/read/pzfvwbrjswhz#d2b10f](https://www.overleaf.com/read/pzfvwbrjswhz#d2b10f) (Max 10 pages, all mandatory sections included).
2. **5-Minute YouTube Demo Video Script:**
   * File: [`YOUTUBE_DEMO_SCRIPT.md`](file:///c:/Users/PC/Downloads/pond%20planning/YOUTUBE_DEMO_SCRIPT.md)
   * Section-by-section timestamps, narration script, visual cues, and feature demonstration steps.
3. **Monochrome Academic Document:**
   * File: [`PROJECT_REPORT.docx`](file:///c:/Users/PC/Downloads/pond%20planning/PROJECT_REPORT.docx) & [`REPORT.md`](file:///c:/Users/PC/Downloads/pond%20planning/REPORT.md).
