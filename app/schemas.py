"""Pydantic request and response schemas for the Pond Catchment Analysis API."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PondSiteResponse(BaseModel):
    """Geographic location and elevation of the identified optimal pond site."""
    lat: float = Field(..., description="WGS84 Latitude of pond outlet", json_schema_extra={"example": 21.251833})
    lon: float = Field(..., description="WGS84 Longitude of pond outlet", json_schema_extra={"example": 81.296571})
    elevation_m: float = Field(..., description="Surface elevation in meters at pond site", json_schema_extra={"example": 270.0})
    flow_accumulation_cells: int = Field(..., description="Upstream flow accumulation cell count", json_schema_extra={"example": 310})


class CatchmentResponse(BaseModel):
    """Delineated upstream catchment hydrological statistics, water volume, and boundary geometry."""
    area_m2: float = Field(..., description="Upstream catchment surface area in square meters", json_schema_extra={"example": 44300.0})
    area_hectares: float = Field(..., description="Catchment area in hectares", json_schema_extra={"example": 4.43})
    mean_slope_pct: float = Field(..., description="Mean terrain slope percentage across catchment", json_schema_extra={"example": 4.8})
    max_slope_pct: float = Field(..., description="Maximum terrain slope percentage across catchment", json_schema_extra={"example": 28.62})
    min_elevation_m: float = Field(..., description="Minimum elevation within catchment", json_schema_extra={"example": 270.0})
    max_elevation_m: float = Field(..., description="Maximum elevation within catchment", json_schema_extra={"example": 293.0})
    relief_m: float = Field(..., description="Total catchment topographic relief in meters", json_schema_extra={"example": 23.0})
    watershed_cell_count: int = Field(..., description="Total number of raster cells comprising the watershed", json_schema_extra={"example": 443})
    expected_water_volume_m3: Optional[float] = Field(
        default=None,
        description="Expected annual harvestable water volume in cubic meters (m³)",
        json_schema_extra={"example": 15505.0},
    )
    expected_water_volume_liters: Optional[float] = Field(
        default=None,
        description="Expected annual harvestable water volume in liters",
        json_schema_extra={"example": 15505000.0},
    )
    expected_water_volume_million_liters: Optional[float] = Field(
        default=None,
        description="Expected annual harvestable water volume in Million Liters (ML)",
        json_schema_extra={"example": 15.51},
    )
    rainfall_mm: Optional[float] = Field(
        default=1000.0,
        description="Annual precipitation in millimeters used for volume estimation",
        json_schema_extra={"example": 1000.0},
    )
    runoff_coefficient: Optional[float] = Field(
        default=0.35,
        description="Runoff coefficient C used for volume estimation",
        json_schema_extra={"example": 0.35},
    )
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
    selected_land_area_applied: Optional[bool] = Field(
        default=False,
        description="True if analysis was focused/filtered to a user-selected land area",
        json_schema_extra={"example": False},
    )
    pond_site: PondSiteResponse
    catchment: CatchmentResponse
    processing_time_ms: int = Field(..., description="Total processing time in milliseconds", json_schema_extra={"example": 2446})


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(default="ok", json_schema_extra={"example": "ok"})
