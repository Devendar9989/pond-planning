"""Watershed delineation and GeoJSON boundary polygon generation with water volume calculation."""

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from pyproj import Transformer
import shapely.geometry
import shapely.ops

from app.dem.dem_builder import DEMGrid
from app.terrain.hydrology import NEIGHBOR_OFFSETS, HydrologyResult


@dataclass
class CatchmentResult:
    """Delineated catchment area results, water volume estimation, and boundary."""
    area_m2: float
    area_hectares: float
    mean_slope_pct: float
    max_slope_pct: float
    min_elevation_m: float
    max_elevation_m: float
    relief_m: float
    watershed_cell_count: int
    expected_water_volume_m3: float
    expected_water_volume_liters: float
    expected_water_volume_million_liters: float
    rainfall_mm: float
    runoff_coefficient: float
    boundary_geojson: Dict[str, Any]
    catchment_mask: np.ndarray


def _reproject_polygon_to_wgs84(
    geom: shapely.geometry.base.BaseGeometry,
    transformer: Transformer,
) -> Dict[str, Any]:
    """
    Transforms a Shapely geometry from UTM coordinates to WGS84 (lon, lat) GeoJSON.
    """
    def _transform_coords(x, y, z=None):
        lons, lats = transformer.transform(x, y)
        return (lons, lats)

    projected_geom = shapely.ops.transform(_transform_coords, geom)
    return shapely.geometry.mapping(projected_geom)


def delineate_catchment(
    dem: DEMGrid,
    hydro: HydrologyResult,
    outlet_row: int,
    outlet_col: int,
    rainfall_mm: float = 1000.0,
    runoff_coefficient: float = 0.35,
) -> CatchmentResult:
    """
    Traces upstream contributing area from the given outlet cell using reverse D8 flow direction,
    computes watershed statistics, estimates harvestable water volume, and builds a GeoJSON polygon boundary.

    Hydrological Runoff Formula:
        Volume (m³) = Catchment Area (m²) * (Rainfall (mm) / 1000) * Runoff Coefficient (C)
        Volume (Liters) = Volume (m³) * 1000
        Volume (Million Liters / ML) = Volume (Liters) / 1,000,000

    Args:
        dem: DEMGrid containing spatial coordinates and projection information.
        hydro: HydrologyResult with D8 flow directions and slope.
        outlet_row: Row index of the chosen pond site.
        outlet_col: Column index of the chosen pond site.
        rainfall_mm: Annual or seasonal precipitation in mm (default 1000.0 mm).
        runoff_coefficient: Rational method runoff coefficient C (default 0.35 for agricultural loam).

    Returns:
        CatchmentResult containing area, volume, relief, slopes, cell count, and GeoJSON boundary.
    """
    nrows, ncols = dem.grid.shape
    flow_dir = hydro.flow_direction
    catchment_mask = np.zeros((nrows, ncols), dtype=bool)

    # 1. Backward BFS traversal upstream from outlet
    queue = deque([(outlet_row, outlet_col)])
    catchment_mask[outlet_row, outlet_col] = True

    while queue:
        curr_r, curr_c = queue.popleft()

        # Check all 8 potential upstream neighbors
        for nr_offset, nc_offset in NEIGHBOR_OFFSETS:
            nr = curr_r + nr_offset
            nc = curr_c + nc_offset

            if 0 <= nr < nrows and 0 <= nc < ncols and not catchment_mask[nr, nc]:
                d = flow_dir[nr, nc]
                if d != -1:
                    target_r = nr + NEIGHBOR_OFFSETS[d][0]
                    target_c = nc + NEIGHBOR_OFFSETS[d][1]
                    if target_r == curr_r and target_c == curr_c:
                        catchment_mask[nr, nc] = True
                        queue.append((nr, nc))

    # 2. Catchment statistics & Water Volume Calculation
    cell_area = dem.resolution_m ** 2
    total_cells = int(np.sum(catchment_mask))
    area_m2 = float(total_cells * cell_area)
    area_hectares = round(area_m2 / 10000.0, 2)

    # Standard Hydrological Rational Runoff Volume Calculation
    effective_coeff = float(np.clip(runoff_coefficient, 0.01, 1.0))
    effective_rainfall = max(float(rainfall_mm), 0.0)
    expected_vol_m3 = round(area_m2 * (effective_rainfall / 1000.0) * effective_coeff, 2)
    expected_vol_liters = round(expected_vol_m3 * 1000.0, 2)
    expected_vol_ml = round(expected_vol_liters / 1_000_000.0, 2)

    catchment_elevs = dem.grid[catchment_mask]
    if total_cells > 0:
        min_elev = float(np.min(catchment_elevs))
        max_elev = float(np.max(catchment_elevs))
        relief = float(max_elev - min_elev)
        mean_slope = float(np.mean(hydro.slope_pct[catchment_mask]))
        max_slope = float(np.max(hydro.slope_pct[catchment_mask]))
    else:
        min_elev = float(dem.grid[outlet_row, outlet_col])
        max_elev = min_elev
        relief = 0.0
        mean_slope = 0.0
        max_slope = 0.0

    # 3. Vector boundary polygon generation
    res = dem.resolution_m
    half_res = res / 2.0
    cell_boxes = []

    rows, cols = np.where(catchment_mask)
    for r, c in zip(rows, cols):
        x = dem.x_coords[c]
        y = dem.y_coords[r]
        cell_boxes.append(
            shapely.geometry.box(x - half_res, y - half_res, x + half_res, y + half_res)
        )

    if cell_boxes:
        merged_poly = shapely.unary_union(cell_boxes)
        # Simplify slightly with half-resolution tolerance to smooth raster staircasing
        simplified_poly = merged_poly.simplify(half_res, preserve_topology=True)
    else:
        # Fallback single point box
        x = dem.x_coords[outlet_col]
        y = dem.y_coords[outlet_row]
        simplified_poly = shapely.geometry.box(x - half_res, y - half_res, x + half_res, y + half_res)

    transformer_to_wgs84 = Transformer.from_crs(f"EPSG:{dem.utm_epsg}", "EPSG:4326", always_xy=True)
    geojson_geom = _reproject_polygon_to_wgs84(simplified_poly, transformer_to_wgs84)

    return CatchmentResult(
        area_m2=round(area_m2, 2),
        area_hectares=area_hectares,
        mean_slope_pct=round(mean_slope, 2),
        max_slope_pct=round(max_slope, 2),
        min_elevation_m=round(min_elev, 2),
        max_elevation_m=round(max_elev, 2),
        relief_m=round(relief, 2),
        watershed_cell_count=total_cells,
        expected_water_volume_m3=expected_vol_m3,
        expected_water_volume_liters=expected_vol_liters,
        expected_water_volume_million_liters=expected_vol_ml,
        rainfall_mm=effective_rainfall,
        runoff_coefficient=effective_coeff,
        boundary_geojson=geojson_geom,
        catchment_mask=catchment_mask,
    )
