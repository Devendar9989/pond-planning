"""Pydantic request and response schemas for the Pond Catchment Analysis API."""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class PondSiteResponse(BaseModel):
    """Geographic location and elevation of the identified optimal pond site."""
    lat: float = Field(..., description="WGS84 Latitude of pond outlet", json_schema_extra={"example": 21.244413})
    lon: float = Field(..., description="WGS84 Longitude of pond outlet", json_schema_extra={"example": 81.291006})
    elevation_m: float = Field(..., description="Surface elevation in meters at pond site", json_schema_extra={"example": 275.0})
    flow_accumulation_cells: int = Field(..., description="Upstream flow accumulation cell count", json_schema_extra={"example": 166})


class CatchmentResponse(BaseModel):
    """Delineated upstream catchment hydrological statistics and boundary geometry."""
    area_m2: float = Field(..., description="Upstream catchment surface area in square meters", json_schema_extra={"example": 16600.0})
    area_hectares: float = Field(..., description="Catchment area in hectares", json_schema_extra={"example": 1.66})
    mean_slope_pct: float = Field(..., description="Mean terrain slope percentage across catchment", json_schema_extra={"example": 3.58})
    max_slope_pct: float = Field(..., description="Maximum terrain slope percentage across catchment", json_schema_extra={"example": 10.93})
    min_elevation_m: float = Field(..., description="Minimum elevation within catchment", json_schema_extra={"example": 275.0})
    max_elevation_m: float = Field(..., description="Maximum elevation within catchment", json_schema_extra={"example": 281.0})
    relief_m: float = Field(..., description="Total catchment topographic relief in meters", json_schema_extra={"example": 6.0})
    watershed_cell_count: int = Field(..., description="Total number of raster cells comprising the watershed", json_schema_extra={"example": 166})
    boundary_geojson: Dict[str, Any] = Field(
        ...,
        description="GeoJSON Polygon or MultiPolygon representing the catchment boundary in WGS84 coordinates",
    )


class AnalyzeContourResponse(BaseModel):
    """Complete analysis output response payload."""
    contour_interval_m: float = Field(..., description="Detected contour interval in meters", json_schema_extra={"example": 1.0})
    elevation_range_m: List[float] = Field(
        ...,
        description="Minimum and maximum terrain elevation [min, max] in meters",
        json_schema_extra={"example": [267.0, 298.0]},
    )
    total_contour_lines: int = Field(..., description="Total contour line features parsed", json_schema_extra={"example": 2710})
    grid_resolution_m: float = Field(..., description="Effective DEM grid resolution in meters", json_schema_extra={"example": 10.0})
    grid_shape: List[int] = Field(..., description="DEM grid dimensions [nrows, ncols]", json_schema_extra={"example": [264, 326]})
    resolution_auto_adjusted: bool = Field(
        ...,
        description="True if resolution was coarsened to protect target memory bounds",
        json_schema_extra={"example": False},
    )
    pond_site: PondSiteResponse
    catchment: CatchmentResponse
    processing_time_ms: int = Field(..., description="Total processing time in milliseconds", json_schema_extra={"example": 2446})


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
