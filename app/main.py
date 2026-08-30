"""FastAPI application for Contour-Based Pond Catchment Analysis API."""

import os
import shutil
import tempfile
import time
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

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

app = FastAPI(
    title="Contour-Based Pond Catchment Analysis API",
    description=(
        "Production backend API to parse contour maps (KML/KMZ), generate metric DEMs, "
        "execute hydrological terrain analysis, identify optimal farm pond sites, "
        "and delineate upstream catchment boundaries."
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


@app.post(
    "/analyzeContour",
    response_model=AnalyzeContourResponse,
    tags=["Catchment Analysis"],
    summary="Analyze contour map and delineate pond catchment",
    responses={
        200: {"description": "Catchment analysis successfully computed."},
        400: {"description": "Invalid file format, corrupt XML, or invalid parameters."},
        422: {"description": "No viable pond site satisfies the minimum catchment criteria."},
        500: {"description": "Internal processing error during terrain analysis."},
    },
)
async def analyze_contour(
    file: UploadFile = File(..., description="KML or KMZ contour map file"),
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
) -> AnalyzeContourResponse:
    """
    Accepts a KML/KMZ contour map upload, analyzes terrain topography,
    identifies the optimal pond location, and computes the upstream catchment boundary.
    """
    start_time = time.perf_counter()

    filename = file.filename or ""
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
            while chunk := await file.read(64 * 1024):  # 64KB chunks
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

        # 3. Hydrological terrain analysis (Priority-flood, D8, flow accumulation)
        try:
            hydro = analyze_terrain(dem.grid, dem.resolution_m)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed during hydrological terrain analysis: {str(e)}",
            )

        # 4. Select optimal pond location
        try:
            min_area = (
                min_catchment_area_m2
                if min_catchment_area_m2 and min_catchment_area_m2 > 0
                else DEFAULT_MIN_CATCHMENT_AREA_M2
            )
            pond = select_pond_site(dem, hydro, min_catchment_area_m2=min_area)
        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Pond site selection could not be fulfilled: {str(e)}",
            )

        # 5. Delineate upstream catchment and generate GeoJSON polygon
        try:
            catchment = delineate_catchment(dem, hydro, pond.row, pond.col)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed during catchment delineation: {str(e)}",
            )

        elapsed_ms = int((time.perf_counter() - start_time) * 1000)

        response = AnalyzeContourResponse(
            contour_interval_m=dataset.contour_interval_m,
            elevation_range_m=[dataset.elevation_range[0], dataset.elevation_range[1]],
            total_contour_lines=dataset.total_contour_lines,
            grid_resolution_m=dem.resolution_m,
            grid_shape=[int(dem.grid.shape[0]), int(dem.grid.shape[1])],
            resolution_auto_adjusted=dem.resolution_auto_adjusted,
            pond_site=PondSiteResponse(
                lat=pond.lat,
                lon=pond.lon,
                elevation_m=pond.elevation_m,
                flow_accumulation_cells=int(pond.flow_accum_cells),
            ),
            catchment=CatchmentResponse(
                area_m2=catchment.area_m2,
                area_hectares=catchment.area_hectares,
                mean_slope_pct=catchment.mean_slope_pct,
                max_slope_pct=catchment.max_slope_pct,
                min_elevation_m=catchment.min_elevation_m,
                max_elevation_m=catchment.max_elevation_m,
                relief_m=catchment.relief_m,
                watershed_cell_count=catchment.watershed_cell_count,
                boundary_geojson=catchment.boundary_geojson,
            ),
            processing_time_ms=elapsed_ms,
        )
        return response

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
