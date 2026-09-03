"""Integration tests for FastAPI endpoints."""

import io
import os
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)
SAMPLE_KML_PATH = os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml")


def test_health_endpoint():
    """Verify health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_analyze_contour_invalid_file_extension():
    """Verify 400 error on non-KML/KMZ upload."""
    files = {"file": ("test.txt", io.BytesIO(b"random text content"), "text/plain")}
    response = client.post("/analyzeContour", files=files)
    assert response.status_code == 400
    assert "Unsupported file format" in response.json()["detail"]


def test_analyze_contour_corrupt_kml():
    """Verify 400 error on corrupt XML content."""
    files = {"file": ("corrupt.kml", io.BytesIO(b"not xml content"), "application/vnd.google-earth.kml+xml")}
    response = client.post("/analyzeContour", files=files)
    assert response.status_code == 400
    assert "Failed to parse" in response.json()["detail"]


def test_analyze_contour_sample_kml_success():
    """Full integration test of POST /analyzeContour with the sample contour file."""
    assert os.path.exists(SAMPLE_KML_PATH), "contours_1m.kml must exist"

    with open(SAMPLE_KML_PATH, "rb") as f:
        files = {"file": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")}
        data = {"resolution_m": "10.0", "min_catchment_area_m2": "500.0"}
        response = client.post("/analyzeContour", files=files, data=data)

    assert response.status_code == 200
    payload = response.json()

    # Validate high-level metadata
    assert payload["contour_interval_m"] == pytest.approx(1.0, rel=1e-2)
    assert payload["elevation_range_m"][0] == pytest.approx(267.0, rel=1e-2)
    assert payload["elevation_range_m"][1] == pytest.approx(298.0, rel=1e-2)
    assert payload["total_contour_lines"] == 2710
    assert payload["grid_resolution_m"] == 10.0
    assert payload["grid_shape"] == [264, 326]
    assert not payload["resolution_auto_adjusted"]
    assert payload["processing_time_ms"] > 0

    # Validate pond site
    pond = payload["pond_site"]
    assert 81.0 <= pond["lon"] <= 82.0
    assert 21.0 <= pond["lat"] <= 22.0
    assert 267.0 <= pond["elevation_m"] <= 298.0
    assert pond["flow_accumulation_cells"] > 0

    # Validate catchment
    catchment = payload["catchment"]
    assert catchment["area_m2"] >= 500.0
    assert catchment["area_hectares"] == pytest.approx(catchment["area_m2"] / 10000.0, rel=1e-3)
    assert catchment["mean_slope_pct"] >= 0.0
    assert catchment["max_slope_pct"] >= catchment["mean_slope_pct"]
    assert catchment["min_elevation_m"] <= catchment["max_elevation_m"]
    assert catchment["relief_m"] == pytest.approx(catchment["max_elevation_m"] - catchment["min_elevation_m"], rel=1e-3)
    assert catchment["watershed_cell_count"] > 0

    # Validate GeoJSON structure
    geojson = catchment["boundary_geojson"]
    assert geojson["type"] in ["Polygon", "MultiPolygon"]
    assert len(geojson["coordinates"]) > 0


def test_analyze_contour_with_contour_map_param():
    """Verify POST /analyzeContour works with primary parameter name 'contour_map'."""
    assert os.path.exists(SAMPLE_KML_PATH), "contours_1m.kml must exist"

    with open(SAMPLE_KML_PATH, "rb") as f:
        files = {"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")}
        data = {"resolution_m": "10.0", "min_catchment_area_m2": "500.0"}
        response = client.post("/analyzeContour", files=files, data=data)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_contour_lines"] == 2710
    assert payload["pond_site"]["flow_accumulation_cells"] > 0
    assert payload["catchment"]["area_m2"] >= 500.0


def test_analyze_contour_missing_file():
    """Verify 400 error when neither contour_map nor file is provided."""
    response = client.post("/analyzeContour", files={}, data={"resolution_m": "10.0"})
    assert response.status_code == 400
    assert "Missing contour map file" in response.json()["detail"]
