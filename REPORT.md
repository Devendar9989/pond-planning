# Project Report — Contour-Based Pond Catchment Analysis API

**Course / Context:** System Design Assignment  
**Service Status:** 🟢 Live & Deployed  
**Deployment Target:** Linux Server (`10.1.75.51:3000`)  

---

## 1. Project Links & Working API URLs

| Resource | URL / Location |
|---|---|
| **GitHub Repository** | `https://github.com/<username>/pond_planning` *(Remote clone at `/home/student/pond_panning`)* |
| **Working API Route (Primary)** | `http://10.1.75.51:3000/analyzeContour` |
| **Health Check Route** | `http://10.1.75.51:3000/health` |
| **Interactive API Documentation (Swagger)** | `http://10.1.75.51:3000/docs` |
| **Alternative OpenAPI Schema** | `http://10.1.75.51:3000/redoc` |

---

## 2. Catchment Estimation & Hydrological Approach

The backend implements a pure **NumPy / SciPy** layered geospatial and hydrological processing pipeline designed specifically to operate within strict resource constraints (**512MB RAM, 1 vCPU, 1.5GB storage**), avoiding heavy C/C++ GIS bindings (GDAL/rasterio). Every metric, coordinate, and polygon is computed dynamically at request time with **zero hardcoded values**.

```
Upload (.kml/.kmz)
       │
       ▼
[1] Streaming Upload & Namespace-Agnostic Parser (`app/parser/kml_parser.py`)
       │ • Streams file directly to disk to prevent RAM spikes
       │ • Uses lxml XPath with local-name() matching to extract coordinates & elevation
       │ • Extracts total contour features and dynamically detects contour interval
       ▼
[2] Metric Projection & DEM Builder (`app/dem/dem_builder.py`)
       │ • Calculates centroid and auto-projects WGS84 coordinates to local metric UTM zone
       │ • Auto-Coarsening Guard Rail: scales resolution if cell count > 150,000 cells
       │ • Linear grid interpolation via scipy.interpolate.griddata with nearest-neighbor hull fill
       ▼
[3] Hydrological Terrain Engine (`app/terrain/hydrology.py`)
       │ • Priority-Flood Depression Filling: heapq-based O(N log N) outward spill routing
       │ • 2nd-Order Terrain Slope: gradient magnitude and slope percentage
       │ • D8 Flow Direction: steepest descent routing with flat plateau resolution
       │ • Topological Flow Accumulation: in-degree directed acyclic graph traversal in O(N) time
       ▼
[4] Multi-Criteria Pond Siting & Catchment Delineation (`app/pond/`)
       │ • Multi-Criteria Scoring: High Flow Accumulation + Flatness/Low Slope + Natural Sink Depth
       │ • Reverse-D8 BFS Watershed Tracing: delineates all upstream contributing cells
       │ • Vector Polygon Conversion: Shapely unary_union + WGS84 reprojection -> GeoJSON Polygon
       ▼
JSON Response Builder (`app/schemas.py`, `app/main.py`)
```

### Key Technical Innovations:
1. **Priority-Flood Pit Filling**: Eliminates artificial DEM micro-sinks using an $O(N \log N)$ priority queue, ensuring uninterrupted drainage to downstream pour points.
2. **Topological In-Degree Traversal**: Computes upstream flow accumulation across the entire grid without recursion or stack-overflow risk in $O(N)$ operations.
3. **Auto-Coarsening Guard Rail**: Safeguards the 512MB RAM ceiling by auto-scaling grid resolution if map dimensions exceed memory bounds.
4. **Natural Hollow Recognition**: Boosts scoring for natural storage depressions and concave hollows while filtering out margin border cells.

---

## 3. Demonstration Using the Provided Contour Map (`contours_1m.kml`)

### Request Command:
```bash
curl -X POST "http://10.1.75.51:3000/analyzeContour" \
  -F "file=@contours_1m.kml" \
  -F "resolution_m=10.0" \
  -F "min_catchment_area_m2=500.0"
```

### Actual Live Response Payload (HTTP 200 OK):
```json
{
  "contour_interval_m": 1.0,
  "elevation_range_m": [
    267.0,
    298.0
  ],
  "total_contour_lines": 2710,
  "grid_resolution_m": 10.0,
  "grid_shape": [
    264,
    326
  ],
  "resolution_auto_adjusted": false,
  "pond_site": {
    "lat": 21.251833,
    "lon": 81.296571,
    "elevation_m": 270.0,
    "flow_accumulation_cells": 310
  },
  "catchment": {
    "area_m2": 44300.0,
    "area_hectares": 4.43,
    "mean_slope_pct": 4.8,
    "max_slope_pct": 28.62,
    "min_elevation_m": 270.0,
    "max_elevation_m": 293.0,
    "relief_m": 23.0,
    "watershed_cell_count": 443,
    "boundary_geojson": {
      "type": "Polygon",
      "coordinates": [
        [
          [81.295562, 21.25179],
          [81.295562, 21.25206],
          [81.295466, 21.25206],
          [81.295466, 21.252241],
          [81.295274, 21.252331],
          [81.295275, 21.252602],
          [81.295179, 21.252602],
          [81.295179, 21.252782],
          [81.295275, 21.252782],
          [81.295275, 21.252873],
          [81.295468, 21.252962],
          [81.295564, 21.253143],
          [81.295661, 21.253142],
          [81.295661, 21.253323],
          [81.295757, 21.253323],
          [81.295757, 21.253413],
          [81.29595, 21.253412],
          [81.296045, 21.253232],
          [81.297295, 21.25323],
          [81.297295, 21.253049],
          [81.297487, 21.252959],
          [81.297582, 21.252598],
          [81.297774, 21.252507],
          [81.297774, 21.252417],
          [81.297678, 21.252417],
          [81.297678, 21.252237],
          [81.297582, 21.252237],
          [81.297581, 21.251966],
          [81.297485, 21.251967],
          [81.297485, 21.251786],
          [81.296619, 21.251788],
          [81.296619, 21.251697],
          [81.296523, 21.251698],
          [81.296522, 21.251157],
          [81.296714, 21.251066],
          [81.296714, 21.250976],
          [81.296522, 21.250976],
          [81.296521, 21.250886],
          [81.296329, 21.250886],
          [81.296329, 21.250796],
          [81.296137, 21.250796],
          [81.29604, 21.250616],
          [81.295944, 21.250616],
          [81.295944, 21.250707],
          [81.29604, 21.250707],
          [81.296041, 21.251067],
          [81.295849, 21.251158],
          [81.295753, 21.251519],
          [81.295657, 21.251519],
          [81.295658, 21.251789],
          [81.295562, 21.25179]
        ]
      ]
    }
  },
  "processing_time_ms": 11024
}
```

### Result Analysis:
- **Optimal Pond Location:** Lat `21.251833°N`, Lon `81.296571°E`, Elevation `270.0m`.
- **Topographic Relief & Storage:** Contributing watershed has `23.0m` of vertical relief ($270\text{m} \rightarrow 293\text{m}$), collecting runoff from a mean surface slope of `4.8%`.
- **Catchment Extent:** $443 \text{ cells} \times (10\text{m})^2 = 44,300\text{ m}^2 = 4.43\text{ hectares}$.
- **Topological Integrity:** Catchment boundary forms a strictly closed, valid WGS84 GeoJSON polygon.

---

## 4. API Documentation

### Endpoint: `GET /health`
* **Purpose:** Service health and uptime monitoring.
* **Response (200 OK):**
  ```json
  {
    "status": "ok"
  }
  ```

---

### Endpoint: `POST /analyzeContour`
* **Purpose:** Uploads a contour map file, computes DEM and terrain hydrology, identifies optimal pond site, and delineates catchment.
* **Content-Type:** `multipart/form-data`

#### Request Parameters:
| Parameter | Type | Required | Default | Description |
|---|---|---|---|---|
| `file` | `UploadFile` | **Yes** | — | `.kml` or `.kmz` contour map file |
| `resolution_m` | `float` | No | `10.0` | Target raster DEM cell resolution in meters |
| `min_catchment_area_m2` | `float` | No | `500.0` | Minimum upstream catchment area threshold |

#### Response Attributes:
| Field | Type | Description |
|---|---|---|
| `contour_interval_m` | `float` | Detected contour interval in meters |
| `elevation_range_m` | `[float, float]` | Minimum and maximum terrain elevations `[min, max]` |
| `total_contour_lines` | `int` | Total contour feature placemarks parsed |
| `grid_resolution_m` | `float` | Effective DEM grid cell resolution |
| `grid_shape` | `[int, int]` | 2D raster dimensions `[nrows, ncols]` |
| `resolution_auto_adjusted` | `bool` | `true` if resolution was coarsened to protect RAM |
| `pond_site.lat` | `float` | WGS84 Latitude of pond outlet |
| `pond_site.lon` | `float` | WGS84 Longitude of pond outlet |
| `pond_site.elevation_m` | `float` | Surface elevation at pond outlet |
| `pond_site.flow_accumulation_cells` | `int` | Number of upstream raster cells draining into outlet |
| `catchment.area_m2` | `float` | Catchment surface area in $\text{m}^2$ |
| `catchment.area_hectares` | `float` | Catchment surface area in hectares |
| `catchment.mean_slope_pct` | `float` | Average surface slope percentage |
| `catchment.max_slope_pct` | `float` | Peak slope percentage within catchment |
| `catchment.min_elevation_m` | `float` | Lowest elevation within catchment basin |
| `catchment.max_elevation_m` | `float` | Highest ridge elevation within catchment basin |
| `catchment.relief_m` | `float` | Vertical elevation relief (`max_elev - min_elev`) |
| `catchment.watershed_cell_count` | `int` | Total raster cells comprising the watershed |
| `catchment.boundary_geojson` | `object` | GeoJSON `Polygon` boundary in WGS84 coordinates |
| `processing_time_ms` | `int` | Total execution runtime in milliseconds |

#### Error Status Codes:
* `400 Bad Request`: Invalid file format, unsupported extension, corrupt XML, or negative resolution.
* `422 Unprocessable Entity`: No valid pond site satisfies minimum catchment criteria (e.g. perfectly flat terrain).
* `500 Internal Server Error`: Processing failure during interpolation or geometry generation.
