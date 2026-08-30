"""Unit tests for hydrological terrain analysis algorithms."""

import pytest
import numpy as np
from app.terrain.hydrology import (
    fill_depressions,
    calculate_slope,
    compute_d8_flow_direction,
    compute_flow_accumulation,
    analyze_terrain,
)


def test_fill_depressions_synthetic_bowl():
    """Verify priority-flood fills an enclosed sink/bowl up to the pour point."""
    # 5x5 grid with high outer rim (10.0), inner depression (2.0), and a spill notch (5.0)
    grid = np.array([
        [10.0, 10.0, 10.0, 10.0, 10.0],
        [10.0,  2.0,  2.0,  2.0, 10.0],
        [ 5.0,  2.0,  1.0,  2.0, 10.0],  # notch on left edge at 5.0
        [10.0,  2.0,  2.0,  2.0, 10.0],
        [10.0, 10.0, 10.0, 10.0, 10.0],
    ], dtype=np.float32)

    filled = fill_depressions(grid)
    # The center pit (1.0) and surrounding inner cells (2.0) should be raised to spill notch elevation (5.0)
    assert filled[2, 2] == pytest.approx(5.0)
    assert filled[1, 1] == pytest.approx(5.0)
    assert filled[3, 3] == pytest.approx(5.0)
    assert filled[2, 0] == pytest.approx(5.0)


def test_v_valley_flow_accumulation():
    """Verify flow accumulation increases monotonically along a drainage valley."""
    # V-channel sloped from row 0 to row 4, with valley center at col 2
    # Elevations:
    # Row 0: [15, 12, 10, 12, 15]
    # Row 1: [14, 11,  9, 11, 14]
    # Row 2: [13, 10,  8, 10, 13]
    # Row 3: [12,  9,  7,  9, 12]
    # Row 4: [11,  8,  6,  8, 11]
    nrows, ncols = 5, 5
    grid = np.zeros((nrows, ncols), dtype=np.float32)
    for r in range(nrows):
        for c in range(ncols):
            dist_from_center = abs(c - 2)
            grid[r, c] = 10.0 - r + dist_from_center * 2.0

    res = analyze_terrain(grid, resolution_m=10.0)

    # Valley center cells should have high flow accumulation
    valley_accum = [res.flow_accumulation[r, 2] for r in range(nrows)]
    # Accumulation down the valley should increase
    assert valley_accum[0] < valley_accum[1] < valley_accum[2] < valley_accum[3]
    assert valley_accum[-1] >= 10.0  # Captures drainage from entire valley


def test_calculate_slope():
    """Verify slope calculation on a known uniform planar slope."""
    # 10m resolution, 1m drop per 10m -> 10% slope
    grid = np.array([
        [10.0, 10.0, 10.0],
        [ 9.0,  9.0,  9.0],
        [ 8.0,  8.0,  8.0],
    ], dtype=np.float32)

    slope_pct, _ = calculate_slope(grid, resolution_m=10.0)
    # Center cell slope should be 10%
    assert slope_pct[1, 1] == pytest.approx(10.0, rel=1e-2)
