"""Digital Elevation Model (DEM) builder with dynamic UTM projection and auto-coarsening."""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np
from pyproj import Transformer
from scipy.interpolate import griddata

from app.config import DEFAULT_RESOLUTION_M, MAX_GRID_CELLS
from app.parser.kml_parser import ContourDataset


@dataclass
class DEMGrid:
    """Represents a regular 2D Digital Elevation Model in metric UTM projection."""
    grid: np.ndarray          # 2D array (nrows, ncols), row 0 is North (max_y)
    x_coords: np.ndarray      # 1D array of X coordinates (West to East)
    y_coords: np.ndarray      # 1D array of Y coordinates (North to South)
    resolution_m: float       # Cell size in meters
    resolution_auto_adjusted: bool
    utm_epsg: int             # UTM EPSG code used for metric projection
    bounds_utm: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)


def get_utm_epsg(lon_center: float, lat_center: float) -> int:
    """
    Computes the standard UTM EPSG code for a given WGS84 geographic center point.
    """
    zone = int(np.floor((lon_center + 180.0) / 6.0)) + 1
    if lat_center >= 0:
        return 32600 + zone  # WGS84 / UTM Zone N
    else:
        return 32700 + zone  # WGS84 / UTM Zone S


def _resample_polyline(points: np.ndarray, max_step: float) -> np.ndarray:
    """
    Densifies polyline vertices so that no segment is longer than max_step.
    """
    if len(points) < 2:
        return points

    diffs = np.diff(points, axis=0)
    dists = np.hypot(diffs[:, 0], diffs[:, 1])

    new_points = [points[0]]
    for i, d in enumerate(dists):
        p0 = points[i]
        p1 = points[i + 1]
        if d > max_step:
            num_sub = int(np.ceil(d / max_step))
            alphas = np.linspace(0, 1, num_sub + 1)[1:]
            for alpha in alphas:
                new_points.append(p0 + alpha * (p1 - p0))
        else:
            new_points.append(p1)

    return np.array(new_points)


def build_dem(
    dataset: ContourDataset,
    requested_resolution_m: float = DEFAULT_RESOLUTION_M,
    max_cells: int = MAX_GRID_CELLS,
) -> DEMGrid:
    """
    Projects contour lines to UTM coordinates and interpolates a continuous 2D DEM grid.
    Applies the auto-coarsening guard rail if requested cell count exceeds max_cells.

    Args:
        dataset: Parsed ContourDataset.
        requested_resolution_m: Desired grid cell resolution in meters.
        max_cells: Maximum allowed total grid cells to safeguard memory.

    Returns:
        DEMGrid containing interpolated elevation array and spatial metadata.
    """
    center_lon, center_lat = dataset.centroid
    utm_epsg = get_utm_epsg(center_lon, center_lat)

    # Reproject WGS84 (lon, lat) to UTM (x, y)
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{utm_epsg}", always_xy=True)

    all_pts_list = []
    all_z_list = []

    resample_step = max(requested_resolution_m / 2.0, 5.0)

    for line in dataset.lines:
        coords_arr = np.array(line.coords, dtype=np.float64)
        lons = coords_arr[:, 0]
        lats = coords_arr[:, 1]
        xs, ys = transformer.transform(lons, lats)
        utm_pts = np.column_stack((xs, ys))

        # Densify segments to avoid interpolation gaps
        densified_pts = _resample_polyline(utm_pts, max_step=resample_step)
        all_pts_list.append(densified_pts)
        all_z_list.append(np.full(len(densified_pts), line.elevation, dtype=np.float32))

    points_xy = np.vstack(all_pts_list)
    points_z = np.concatenate(all_z_list)

    min_x, min_y = np.min(points_xy, axis=0)
    max_x, max_y = np.max(points_xy, axis=0)

    width_m = max_x - min_x
    height_m = max_y - min_y

    resolution_m = float(requested_resolution_m)
    resolution_auto_adjusted = False

    # Guard rail: auto-scale resolution if cell count exceeds memory safety ceiling
    estimated_cells = (width_m / resolution_m) * (height_m / resolution_m)
    if estimated_cells > max_cells:
        target_res = float(np.sqrt((width_m * height_m) / max_cells))
        resolution_m = round(max(resolution_m, target_res), 1)
        resolution_auto_adjusted = True

    ncols = max(int(np.ceil(width_m / resolution_m)) + 1, 2)
    nrows = max(int(np.ceil(height_m / resolution_m)) + 1, 2)

    # Coordinates: X goes West -> East, Y goes North -> South (standard raster matrix)
    x_coords = np.linspace(min_x, max_x, ncols, dtype=np.float64)
    y_coords = np.linspace(max_y, min_y, nrows, dtype=np.float64)
    grid_x, grid_y = np.meshgrid(x_coords, y_coords)

    # 1. Linear interpolation on interior
    dem_linear = griddata(
        points_xy,
        points_z,
        (grid_x, grid_y),
        method="linear",
    )

    # 2. Fill perimeter/convex-hull exterior NaNs using nearest neighbor
    nan_mask = np.isnan(dem_linear)
    if np.any(nan_mask):
        dem_nearest = griddata(
            points_xy,
            points_z,
            (grid_x[nan_mask], grid_y[nan_mask]),
            method="nearest",
        )
        dem_linear[nan_mask] = dem_nearest

    elevation_grid = dem_linear.astype(np.float32)

    return DEMGrid(
        grid=elevation_grid,
        x_coords=x_coords,
        y_coords=y_coords,
        resolution_m=resolution_m,
        resolution_auto_adjusted=resolution_auto_adjusted,
        utm_epsg=utm_epsg,
        bounds_utm=(float(min_x), float(min_y), float(max_x), float(max_y)),
    )
