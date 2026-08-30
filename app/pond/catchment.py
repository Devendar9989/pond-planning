"""Watershed delineation and GeoJSON boundary polygon generation."""

from collections import deque
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple
import numpy as np
from pyproj import Transformer
import shapely.geometry
import shapely.ops

from app.dem.dem_builder import DEMGrid
from app.terrain.hydrology import NEIGHBOR_OFFSETS, HydrologyResult


@dataclass
class CatchmentResult:
    """Delineated catchment area results and boundary."""
    area_m2: float
    area_hectares: float
    mean_slope_pct: float
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
) -> CatchmentResult:
    """
    Traces upstream contributing area from the given outlet cell using reverse D8 flow direction,
    computes watershed statistics, and builds a GeoJSON polygon boundary.

    Args:
        dem: DEMGrid containing spatial coordinates and projection information.
        hydro: HydrologyResult with D8 flow directions and slope.
        outlet_row: Row index of the chosen pond site.
        outlet_col: Column index of the chosen pond site.

    Returns:
        CatchmentResult containing area, mean slope, and GeoJSON boundary.
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

    # 2. Catchment statistics
    cell_area = dem.resolution_m ** 2
    total_cells = int(np.sum(catchment_mask))
    area_m2 = float(total_cells * cell_area)
    area_hectares = round(area_m2 / 10000.0, 4)

    mean_slope = float(np.mean(hydro.slope_pct[catchment_mask])) if total_cells > 0 else 0.0

    # 3. Vector boundary polygon generation
    res = dem.resolution_m
    half_res = res / 2.0
    cell_boxes = []

    # Construct shapely box for each cell in catchment
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
        boundary_geojson=geojson_geom,
        catchment_mask=catchment_mask,
    )
