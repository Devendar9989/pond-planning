"""FastAPI application for Contour-Based Pond Catchment Analysis API with Interactive Frontend."""

import json
import os
import shutil
import tempfile
import time
from typing import List, Optional, Tuple

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import DEFAULT_MIN_CATCHMENT_AREA_M2, DEFAULT_RESOLUTION_M, MAX_UPLOAD_SIZE_BYTES
from app.dem.dem_builder import build_dem
from app.parser.kml_parser import parse_kml_or_kmz
from app.pond.catchment import delineate_catchment
from app.pond.selector import select_pond_site
from app.schemas import (
    AnalyzeContourResponse,
    CatchmentResponse,
    HealthResponse,
    PondSiteResponse,
)
from app.terrain.hydrology import analyze_terrain

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
SAMPLE_KML_PATH = os.path.join(BASE_DIR, "..", "contours_1m.kml")

app = FastAPI(
    title="Contour-Based Pond Catchment Analysis API",
    description=(
        "Production backend API and Interactive Front-End to parse contour maps (KML/KMZ), "
        "reconstruct metric DEMs, execute hydrological terrain analysis, identify optimal farm pond sites, "
        "estimate harvestable water collection volume, and delineate upstream catchment boundaries."
    ),
    version="1.0.0",
)

# Enable CORS for cross-origin client integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="Health check endpoint",
)
def health_check() -> HealthResponse:
    """Returns the operational status of the service."""
    return HealthResponse(status="ok")


@app.get(
    "/api/sample-kml",
    tags=["Catchment Analysis"],
    summary="Download or stream the default preloaded contours_1m.kml file",
)
def get_sample_kml():
    """Provides the preloaded reference contours_1m.kml survey map for 1-click frontend demos."""
    if os.path.exists(SAMPLE_KML_PATH):
        return FileResponse(
            SAMPLE_KML_PATH,
            media_type="application/vnd.google-earth.kml+xml",
            filename="contours_1m.kml",
        )
    raise HTTPException(status_code=404, detail="Default sample KML file not found on server.")


def _parse_selected_bounds(bounds_str: Optional[str]) -> Optional[Tuple[float, float, float, float]]:
    """Helper to parse selected_bounds string into (min_lon, min_lat, max_lon, max_lat)."""
    if not bounds_str or not bounds_str.strip():
        return None
    try:
        clean = bounds_str.strip()
        if clean.startswith("[") and clean.endswith("]"):
            coords = json.loads(clean)
            if isinstance(coords, list) and len(coords) == 4:
                return (float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3]))
        elif "," in clean:
            parts = [float(p.strip()) for p in clean.split(",")]
            if len(parts) == 4:
                return (parts[0], parts[1], parts[2], parts[3])
    except Exception:
        pass
    return None


@app.post(
    "/analyzeContour",
    response_model=AnalyzeContourResponse,
    tags=["Catchment Analysis"],
    summary="Analyze contour map, site farm pond, and delineate catchment with water volume",
    responses={
        200: {"description": "Catchment analysis successfully computed."},
        400: {"description": "Invalid file format, corrupt XML, or invalid parameters."},
        422: {"description": "No viable pond site satisfies the minimum catchment criteria."},
        500: {"description": "Internal processing error during terrain analysis."},
    },
)
async def analyze_contour(
    contour_map: Optional[UploadFile] = File(
        default=None,
        description="KML or KMZ contour map file (primary variable name: contour_map)",
    ),
    file: Optional[UploadFile] = File(
        default=None,
        description="Alternative fallback parameter name for KML/KMZ contour map file",
    ),
    resolution_m: Optional[float] = Form(
        default=DEFAULT_RESOLUTION_M,
        description="Target DEM grid resolution in meters (default 10.0)",
        gt=0.0,
    ),
    min_catchment_area_m2: Optional[float] = Form(
        default=DEFAULT_MIN_CATCHMENT_AREA_M2,
        description="Minimum upstream catchment area threshold in square meters (default 500.0)",
        gt=0.0,
    ),
    rainfall_mm: Optional[float] = Form(
        default=1000.0,
        description="Annual or seasonal precipitation in millimeters (default 1000.0)",
        gt=0.0,
    ),
    runoff_coefficient: Optional[float] = Form(
        default=0.35,
        description="Hydrological runoff coefficient C between 0.01 and 1.0 (default 0.35)",
        gt=0.0,
        le=1.0,
    ),
    selected_bounds: Optional[str] = Form(
        default=None,
        description="Optional land area bounding box [min_lon, min_lat, max_lon, max_lat] to constrain pond siting",
    ),
) -> AnalyzeContourResponse:
    """
    Accepts a KML/KMZ contour map upload (under 'contour_map' or 'file'),
    analyzes terrain topography and hydrology, identifies the optimal pond location,
    estimates expected water harvest volume, and computes the upstream catchment boundary.
    """
    upload = contour_map or file
    if upload is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing contour map file. Please upload a KML or KMZ file under variable name 'contour_map'.",
        )

    start_time = time.perf_counter()

    filename = upload.filename or ""
    lower_name = filename.lower()
    if not (lower_name.endswith(".kml") or lower_name.endswith(".kmz")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file format. Please upload a .kml or .kmz file.",
        )

    # Stream upload directly to a temporary file on disk to conserve RAM
    suffix = ".kmz" if lower_name.endswith(".kmz") else ".kml"
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp_file:
            tmp_path = tmp_file.name
            bytes_written = 0
            while chunk := await upload.read(64 * 1024):  # 64KB chunks
                bytes_written += len(chunk)
                if bytes_written > MAX_UPLOAD_SIZE_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Uploaded file exceeds maximum size limit of {MAX_UPLOAD_SIZE_BYTES // (1024*1024)}MB.",
                    )
                tmp_file.write(chunk)

        # 1. Parse KML / KMZ
        try:
            dataset = parse_kml_or_kmz(tmp_path)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse contour file: {str(e)}",
            )

        # 2. Build DEM with dynamic UTM projection and auto-coarsening
        try:
            target_res = resolution_m if resolution_m and resolution_m > 0 else DEFAULT_RESOLUTION_M
            dem = build_dem(dataset, requested_resolution_m=target_res)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed during DEM generation: {str(e)}",
            )

        # 3. Hydrological terrain modeling
        try:
            hydro = analyze_terrain(dem.grid, dem.resolution_m)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed during hydrological analysis: {str(e)}",
            )

        # 4. Parse optional selected land area bounds
        parsed_aoi_bounds = _parse_selected_bounds(selected_bounds)
        land_area_applied = parsed_aoi_bounds is not None

        # 5. Farm pond multi-criteria siting
        try:
            min_area = min_catchment_area_m2 if min_catchment_area_m2 and min_catchment_area_m2 > 0 else DEFAULT_MIN_CATCHMENT_AREA_M2
            pond_site = select_pond_site(
                dem,
                hydro,
                min_catchment_area_m2=min_area,
                selected_bounds=parsed_aoi_bounds,
            )
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Pond siting failed: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Internal error during pond site selection: {str(e)}",
            )

        # 6. Delineate upstream catchment and calculate expected harvestable water volume
        eff_rainfall = rainfall_mm if rainfall_mm and rainfall_mm > 0 else 1000.0
        eff_runoff_c = runoff_coefficient if runoff_coefficient and 0.0 < runoff_coefficient <= 1.0 else 0.35

        try:
            catchment = delineate_catchment(
                dem,
                hydro,
                outlet_row=pond_site.row,
                outlet_col=pond_site.col,
                rainfall_mm=eff_rainfall,
                runoff_coefficient=eff_runoff_c,
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed during catchment delineation: {str(e)}",
            )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        # Assemble final response
        return AnalyzeContourResponse(
            contour_interval_m=float(dataset.contour_interval_m),
            elevation_range_m=[float(dataset.elevation_range[0]), float(dataset.elevation_range[1])],
            total_contour_lines=int(dataset.total_contour_lines),
            grid_resolution_m=float(dem.resolution_m),
            grid_shape=[int(dem.grid.shape[0]), int(dem.grid.shape[1])],
            resolution_auto_adjusted=bool(dem.resolution_auto_adjusted),
            selected_land_area_applied=land_area_applied,
            pond_site=PondSiteResponse(
                lat=float(pond_site.lat),
                lon=float(pond_site.lon),
                elevation_m=float(pond_site.elevation_m),
                flow_accumulation_cells=int(pond_site.flow_accum_cells),
            ),
            catchment=CatchmentResponse(
                area_m2=float(catchment.area_m2),
                area_hectares=float(catchment.area_hectares),
                mean_slope_pct=float(catchment.mean_slope_pct),
                max_slope_pct=float(catchment.max_slope_pct),
                min_elevation_m=float(catchment.min_elevation_m),
                max_elevation_m=float(catchment.max_elevation_m),
                relief_m=float(catchment.relief_m),
                watershed_cell_count=int(catchment.watershed_cell_count),
                expected_water_volume_m3=float(catchment.expected_water_volume_m3),
                expected_water_volume_liters=float(catchment.expected_water_volume_liters),
                expected_water_volume_million_liters=float(catchment.expected_water_volume_million_liters),
                rainfall_mm=float(catchment.rainfall_mm),
                runoff_coefficient=float(catchment.runoff_coefficient),
                boundary_geojson=catchment.boundary_geojson,
            ),
            processing_time_ms=elapsed_ms,
        )

    finally:
        # Cleanup temporary disk files
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass


# Serve Front-End Static UI if static directory exists
if os.path.exists(STATIC_DIR):
    @app.get("/", include_in_schema=False)
    async def serve_root_index():
        index_file = os.path.join(STATIC_DIR, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        return {"status": "ok", "message": "Pond Catchment Analysis API active. Visit /docs for Swagger UI."}

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
