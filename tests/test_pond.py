"""Unit tests for pond site selection and catchment delineation."""

import os
import pytest
import numpy as np
from app.parser.kml_parser import parse_kml_or_kmz
from app.dem.dem_builder import build_dem
from app.terrain.hydrology import analyze_terrain
from app.pond.selector import select_pond_site
from app.pond.catchment import delineate_catchment

SAMPLE_KML_PATH = os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml")


def test_pond_and_catchment_sample_kml():
    """Test full pipeline up to catchment delineation on the real sample KML."""
    dataset = parse_kml_or_kmz(SAMPLE_KML_PATH)
    dem = build_dem(dataset, requested_resolution_m=10.0, max_cells=150_000)
    hydro = analyze_terrain(dem.grid, dem.resolution_m)

    pond = select_pond_site(dem, hydro, min_catchment_area_m2=500.0)

    assert pond.elevation_m >= 267.0
    assert pond.elevation_m <= 298.0
    assert dataset.bounds[0] <= pond.lon <= dataset.bounds[2]
    assert dataset.bounds[1] <= pond.lat <= dataset.bounds[3]
    assert pond.catchment_area_m2 >= 500.0

    catchment = delineate_catchment(dem, hydro, pond.row, pond.col)

    assert catchment.area_m2 >= 500.0
    assert catchment.area_hectares == pytest.approx(catchment.area_m2 / 10000.0)
    assert catchment.mean_slope_pct >= 0.0
    assert "type" in catchment.boundary_geojson
    assert "coordinates" in catchment.boundary_geojson
