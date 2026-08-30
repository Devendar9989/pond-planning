"""Unit tests for DEM builder and projection module."""

import os
import pytest
import numpy as np
from app.parser.kml_parser import parse_kml_or_kmz
from app.dem.dem_builder import build_dem, get_utm_epsg, DEMGrid

SAMPLE_KML_PATH = os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml")


def test_get_utm_epsg():
    # Longitude 81.3, Latitude 21.2 -> Zone 44N -> EPSG:32644
    epsg = get_utm_epsg(81.3, 21.2)
    assert epsg == 32644

    # Southern hemisphere
    epsg_s = get_utm_epsg(81.3, -21.2)
    assert epsg_s == 32744


def test_build_dem_sample_kml():
    dataset = parse_kml_or_kmz(SAMPLE_KML_PATH)
    dem = build_dem(dataset, requested_resolution_m=10.0, max_cells=150_000)

    assert isinstance(dem, DEMGrid)
    assert dem.grid.ndim == 2
    assert not np.isnan(dem.grid).any(), "DEM grid must not contain NaNs"
    assert dem.resolution_m == 10.0
    assert not dem.resolution_auto_adjusted
    assert dem.grid.shape[0] > 100
    assert dem.grid.shape[1] > 100
    assert dem.grid.min() >= 265.0
    assert dem.grid.max() <= 300.0


def test_dem_auto_coarsening_guard_rail():
    dataset = parse_kml_or_kmz(SAMPLE_KML_PATH)
    # Force max_cells to a tiny number to trigger auto-coarsening
    dem = build_dem(dataset, requested_resolution_m=1.0, max_cells=5_000)

    assert dem.resolution_auto_adjusted
    assert dem.resolution_m > 1.0
    assert dem.grid.size <= 10_000
    assert not np.isnan(dem.grid).any()
