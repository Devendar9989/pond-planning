"""Pure NumPy/SciPy hydrological terrain analysis algorithms:
- Priority-Flood depression filling (Barnes et al., 2014)
- 2nd-order terrain slope and aspect calculation
- D8 steepest descent flow direction routing with flat-surface resolution
- O(N) Topological in-degree flow accumulation
"""

from collections import deque
from dataclasses import dataclass
import heapq
from typing import Tuple
import numpy as np

# 8-neighbor directions: (dr, dc)
# Index 0: E, 1: SE, 2: S, 3: SW, 4: W, 5: NW, 6: N, 7: NE
NEIGHBOR_OFFSETS = [
    (0, 1),    # 0: East
    (1, 1),    # 1: South-East
    (1, 0),    # 2: South
    (1, -1),   # 3: South-West
    (0, -1),   # 4: West
    (-1, -1),  # 5: North-West
    (-1, 0),   # 6: North
    (-1, 1),   # 7: North-East
]

SQRT2 = float(np.sqrt(2.0))
NEIGHBOR_DISTANCES = np.array([
    1.0, SQRT2, 1.0, SQRT2, 1.0, SQRT2, 1.0, SQRT2
], dtype=np.float64)


@dataclass
class HydrologyResult:
    """Container for hydrological analysis matrices."""
    filled_dem: np.ndarray        # Depression-free DEM (nrows, ncols)
    slope_pct: np.ndarray         # Slope percentage (nrows, ncols)
    flow_direction: np.ndarray    # D8 flow direction matrix (0..7, or -1 for sink/outlet)
    flow_accumulation: np.ndarray # Upstream cell count matrix (nrows, ncols)


def fill_depressions(dem: np.ndarray) -> np.ndarray:
    """
    Fills digital elevation model depressions using the Priority-Flood algorithm.
    Guarantees monotonic outward drainage to grid boundaries.
    """
    nrows, ncols = dem.shape
    filled = np.copy(dem).astype(np.float64)
    visited = np.zeros((nrows, ncols), dtype=bool)

    # Priority queue: entries are (elevation, row, col)
    pq = []

    # 1. Initialize boundary cells as open spill points
    for r in range(nrows):
        for c in (0, ncols - 1):
            if not visited[r, c]:
                visited[r, c] = True
                heapq.heappush(pq, (filled[r, c], r, c))

    for c in range(ncols):
        for r in (0, nrows - 1):
            if not visited[r, c]:
                visited[r, c] = True
                heapq.heappush(pq, (filled[r, c], r, c))

    # 2. Priority flood inward
    while pq:
        elev, r, c = heapq.heappop(pq)

        for dr, dc in NEIGHBOR_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < nrows and 0 <= nc < ncols and not visited[nr, nc]:
                visited[nr, nc] = True
                if filled[nr, nc] < elev:
                    filled[nr, nc] = elev
                heapq.heappush(pq, (filled[nr, nc], nr, nc))

    return filled.astype(np.float32)


def calculate_slope(dem: np.ndarray, resolution_m: float) -> Tuple[np.ndarray, np.ndarray]:
    """
    Calculates the terrain slope percentage and gradient magnitude using 2nd-order differences.

    Returns:
        (slope_pct, slope_degrees)
    """
    dy, dx = np.gradient(dem, resolution_m)
    grad = np.hypot(dx, dy)
    slope_rad = np.arctan(grad)
    slope_pct = np.tan(slope_rad) * 100.0
    slope_deg = np.degrees(slope_rad)
    return slope_pct.astype(np.float32), slope_deg.astype(np.float32)


def compute_d8_flow_direction(filled_dem: np.ndarray, resolution_m: float) -> np.ndarray:
    """
    Computes D8 flow direction for every cell in the filled DEM.
    Flow direction is stored as an integer from 0 to 7 indicating the steepest descent neighbor,
    or -1 for boundary/outlet cells.
    """
    nrows, ncols = filled_dem.shape
    flow_dir = np.full((nrows, ncols), -1, dtype=np.int8)

    # 1. Primary pass: steepest downward slope
    for r in range(nrows):
        for c in range(ncols):
            z_curr = filled_dem[r, c]
            max_drop = 0.0
            best_dir = -1

            for dir_idx, (dr, dc) in enumerate(NEIGHBOR_OFFSETS):
                nr, nc = r + dr, c + dc
                if 0 <= nr < nrows and 0 <= nc < ncols:
                    dist = NEIGHBOR_DISTANCES[dir_idx] * resolution_m
                    drop = (z_curr - filled_dem[nr, nc]) / dist
                    if drop > max_drop:
                        max_drop = drop
                        best_dir = dir_idx

            flow_dir[r, c] = best_dir

    # 2. Secondary pass: resolve flat areas (flow_dir == -1 in interior) via BFS from lower cells
    unresolved = [(r, c) for r in range(1, nrows - 1) for c in range(1, ncols - 1) if flow_dir[r, c] == -1]
    if unresolved:
        # Distance transform to find path to resolving cells
        resolved_mask = (flow_dir != -1) | (filled_dem == filled_dem.min())
        # Set perimeter as resolved
        resolved_mask[0, :] = True
        resolved_mask[-1, :] = True
        resolved_mask[:, 0] = True
        resolved_mask[:, -1] = True

        queue = deque([(r, c) for r in range(nrows) for c in range(ncols) if resolved_mask[r, c]])
        dist_to_exit = np.full((nrows, ncols), np.inf, dtype=np.float32)
        for r, c in queue:
            dist_to_exit[r, c] = 0.0

        while queue:
            r, c = queue.popleft()
            for dir_idx, (dr, dc) in enumerate(NEIGHBOR_OFFSETS):
                nr, nc = r + dr, c + dc
                if 0 <= nr < nrows and 0 <= nc < ncols:
                    # If neighbor is on same flat elevation and not yet reached
                    if filled_dem[nr, nc] >= filled_dem[r, c] and dist_to_exit[nr, nc] > dist_to_exit[r, c] + 1.0:
                        dist_to_exit[nr, nc] = dist_to_exit[r, c] + 1.0
                        if flow_dir[nr, nc] == -1 and not (nr == 0 or nr == nrows - 1 or nc == 0 or nc == ncols - 1):
                            # Flow from (nr, nc) into (r, c)
                            # Opposite direction index
                            flow_dir[nr, nc] = (dir_idx + 4) % 8
                        queue.append((nr, nc))

    return flow_dir


def compute_flow_accumulation(flow_dir: np.ndarray) -> np.ndarray:
    """
    Computes total upstream flow accumulation (contributing cell count) in O(N) time
    using a topological in-degree traversal.
    """
    nrows, ncols = flow_dir.shape
    in_degree = np.zeros((nrows, ncols), dtype=np.int32)

    # 1. Calculate in-degrees (number of upstream tributaries flowing into each cell)
    for r in range(nrows):
        for c in range(ncols):
            d = flow_dir[r, c]
            if d != -1:
                dr, dc = NEIGHBOR_OFFSETS[d]
                nr, nc = r + dr, c + dc
                if 0 <= nr < nrows and 0 <= nc < ncols:
                    in_degree[nr, nc] += 1

    # 2. Initialize accumulation with 1.0 cell area per pixel
    flow_accum = np.ones((nrows, ncols), dtype=np.float32)

    # 3. Seed queue with headwater cells (in-degree == 0, e.g. mountain ridges)
    queue = deque([
        (r, c) for r in range(nrows) for c in range(ncols) if in_degree[r, c] == 0
    ])

    # 4. Topological traversal downstream
    while queue:
        r, c = queue.popleft()
        d = flow_dir[r, c]
        if d != -1:
            dr, dc = NEIGHBOR_OFFSETS[d]
            nr, nc = r + dr, c + dc
            if 0 <= nr < nrows and 0 <= nc < ncols:
                flow_accum[nr, nc] += flow_accum[r, c]
                in_degree[nr, nc] -= 1
                if in_degree[nr, nc] == 0:
                    queue.append((nr, nc))

    return flow_accum


def analyze_terrain(dem: np.ndarray, resolution_m: float) -> HydrologyResult:
    """
    Executes the complete terrain analysis pipeline:
    1. Depression filling (Priority-Flood)
    2. Terrain slope calculation
    3. D8 flow direction matrix
    4. Topological flow accumulation
    """
    filled_dem = fill_depressions(dem)
    slope_pct, _ = calculate_slope(filled_dem, resolution_m)
    flow_dir = compute_d8_flow_direction(filled_dem, resolution_m)
    flow_accum = compute_flow_accumulation(flow_dir)

    return HydrologyResult(
        filled_dem=filled_dem,
        slope_pct=slope_pct,
        flow_direction=flow_dir,
        flow_accumulation=flow_accum,
    )
