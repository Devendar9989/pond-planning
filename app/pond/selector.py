"""Multi-criteria heuristic pond site selection algorithm with optional land area AOI support."""

from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from pyproj import Transformer

from app.config import BORDER_CELL_MARGIN, DEFAULT_MIN_CATCHMENT_AREA_M2
from app.dem.dem_builder import DEMGrid
from app.terrain.hydrology import HydrologyResult


@dataclass
class PondSiteCandidate:
    """Selected pond outlet site characteristics."""
    row: int
    col: int
    utm_x: float
    utm_y: float
    lat: float
    lon: float
    elevation_m: float
    flow_accum_cells: float
    catchment_area_m2: float
    score: float


def select_pond_site(
    dem: DEMGrid,
    hydro: HydrologyResult,
    min_catchment_area_m2: float = DEFAULT_MIN_CATCHMENT_AREA_M2,
    border_margin: int = BORDER_CELL_MARGIN,
    selected_bounds: Optional[Tuple[float, float, float, float]] = None,
) -> PondSiteCandidate:
    """
    Evaluates candidate cells across the terrain to select the optimal pond location.

    Scoring criteria:
    1. High upstream flow accumulation (concentrated runoff drainage).
    2. Low to moderate slope (natural flat area / depression for water storage).
    3. Interior safety buffer (avoids edge truncation artifacts).
    4. Minimum upstream catchment area threshold.
    5. Optional user-selected land area constraint (AOI bounding box [min_lon, min_lat, max_lon, max_lat]).

    Args:
        dem: Interpolated DEMGrid.
        hydro: HydrologyResult containing filled DEM, slope, and flow accumulation.
        min_catchment_area_m2: Minimum required upstream catchment area in m².
        border_margin: Number of perimeter cells excluded from candidate selection.
        selected_bounds: Optional (min_lon, min_lat, max_lon, max_lat) to restrict pond search area.

    Returns:
        PondSiteCandidate containing geographical coordinates and elevation.

    Raises:
        ValueError: If no valid cell satisfies the minimum catchment area.
    """
    nrows, ncols = dem.grid.shape
    cell_area_m2 = dem.resolution_m ** 2

    # Safety margin check
    margin = max(border_margin, 2)
    if nrows <= 2 * margin or ncols <= 2 * margin:
        margin = 1

    # Candidate mask: interior cells only
    candidate_mask = np.zeros((nrows, ncols), dtype=bool)
    candidate_mask[margin: nrows - margin, margin: ncols - margin] = True

    # Apply selected land area (AOI) bounding box if provided by user
    if selected_bounds is not None:
        min_lon, min_lat, max_lon, max_lat = selected_bounds
        transformer_to_utm = Transformer.from_crs("EPSG:4326", f"EPSG:{dem.utm_epsg}", always_xy=True)
        min_utm_x, min_utm_y = transformer_to_utm.transform(min_lon, min_lat)
        max_utm_x, max_utm_y = transformer_to_utm.transform(max_lon, max_lat)

        utm_xmin, utm_xmax = min(min_utm_x, max_utm_x), max(min_utm_x, max_utm_x)
        utm_ymin, utm_ymax = min(min_utm_y, max_utm_y), max(min_utm_y, max_utm_y)

        # Create 2D coordinate mesh for checking bounds
        xx, yy = np.meshgrid(dem.x_coords, dem.y_coords)
        aoi_mask = (xx >= utm_xmin) & (xx <= utm_xmax) & (yy >= utm_ymin) & (yy <= utm_ymax)

        if np.any(candidate_mask & aoi_mask):
            candidate_mask = candidate_mask & aoi_mask

    # Calculate upstream area for each cell
    accum_cells = hydro.flow_accumulation
    accum_area_m2 = accum_cells * cell_area_m2

    # Filter by minimum catchment area
    valid_mask = candidate_mask & (accum_area_m2 >= min_catchment_area_m2)

    # Fallback if no cell satisfies the area threshold
    if not np.any(valid_mask):
        valid_mask = candidate_mask
        if not np.any(valid_mask):
            raise ValueError("No valid cell found within the selected land area satisfying the minimum catchment area.")

    # Multi-criteria scoring
    # 1. Logarithmic flow accumulation (diminishing returns beyond huge channels)
    log_accum = np.log1p(accum_cells)
    max_log_accum = np.max(log_accum[valid_mask])
    norm_accum = log_accum / (max_log_accum + 1e-6)

    # 2. Slope score: 0-8% slope is ideal for pond channels and storage, slopes >8% receive gradual penalty
    slope = hydro.slope_pct
    norm_slope_score = np.where(
        slope <= 8.0,
        1.0,
        np.clip(1.0 - ((slope - 8.0) / 20.0), 0.0, 1.0),
    )

    # 3. Natural depression / sink score (natural storage hollows)
    depression_depth = np.maximum(hydro.filled_dem - dem.grid, 0.0)
    max_dep = np.max(depression_depth[valid_mask]) if np.any(valid_mask) else 0.0

    if max_dep > 0.5:
        norm_depression = depression_depth / (max_dep + 1e-6)
        score_matrix = (norm_accum * 0.55) + (norm_slope_score * 0.15) + (norm_depression * 0.30)
    else:
        score_matrix = (norm_accum * 0.75) + (norm_slope_score * 0.25)

    score_matrix[~valid_mask] = -np.inf

    best_idx = np.unravel_index(np.argmax(score_matrix), score_matrix.shape)
    best_r, best_c = int(best_idx[0]), int(best_idx[1])

    best_utm_x = float(dem.x_coords[best_c])
    best_utm_y = float(dem.y_coords[best_r])
    elevation = float(dem.grid[best_r, best_c])

    # Convert UTM (x, y) back to WGS84 (lon, lat)
    transformer = Transformer.from_crs(f"EPSG:{dem.utm_epsg}", "EPSG:4326", always_xy=True)
    best_lon, best_lat = transformer.transform(best_utm_x, best_utm_y)

    return PondSiteCandidate(
        row=best_r,
        col=best_c,
        utm_x=best_utm_x,
        utm_y=best_utm_y,
        lat=float(best_lat),
        lon=float(best_lon),
        elevation_m=round(elevation, 2),
        flow_accum_cells=float(accum_cells[best_r, best_c]),
        catchment_area_m2=float(accum_area_m2[best_r, best_c]),
        score=float(score_matrix[best_r, best_c]),
    )
