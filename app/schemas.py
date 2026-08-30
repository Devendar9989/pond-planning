"""Pydantic request and response schemas for the Pond Catchment Analysis API."""

from typing import Any, Dict, List
from pydantic import BaseModel, Field


class PondSiteResponse(BaseModel):
    """Geographic location and elevation of the identified optimal pond site."""
    lat: float = Field(..., description="WGS84 Latitude of pond outlet", json_schema_extra={"example": 21.2521})
    lon: float = Field(..., description="WGS84 Longitude of pond outlet", json_schema_extra={"example": 81.2934})
    elevation_m: float = Field(..., description="Surface elevation in meters at pond site", json_schema_extra={"example": 274.0})


class CatchmentResponse(BaseModel):
    """Delineated upstream catchment hydrological statistics and boundary geometry."""
    area_m2: float = Field(..., description="Upstream catchment surface area in square meters", json_schema_extra={"example": 184500.2})
    area_hectares: float = Field(..., description="Catchment area in hectares", json_schema_extra={"example": 18.45})
    mean_slope_pct: float = Field(..., description="Mean terrain slope percentage across catchment", json_schema_extra={"example": 6.7})
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
    grid_resolution_m: float = Field(..., description="Effective DEM grid resolution in meters", json_schema_extra={"example": 10.0})
    resolution_auto_adjusted: bool = Field(
        ...,
        description="True if resolution was coarsened to protect target memory bounds",
        json_schema_extra={"example": False},
    )
    pond_site: PondSiteResponse
    catchment: CatchmentResponse
    processing_time_ms: int = Field(..., description="Total processing time in milliseconds", json_schema_extra={"example": 842})


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
