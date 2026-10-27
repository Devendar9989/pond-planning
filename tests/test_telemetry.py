"""Unit and integration tests for OpenTelemetry and observability features."""

import os
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
SAMPLE_KML_PATH = os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml")


def test_metrics_endpoint():
    """Verify Prometheus metrics exposition endpoint returns 200 with standard exposition format."""
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "text/plain" in response.headers.get("content-type", "")
    content = response.text
    assert "pondplan_requests_total" in content
    assert "pondplan_analysis_duration_seconds" in content
    assert "pondplan_catchment_area_m2" in content


def test_telemetry_stats_endpoint():
    """Verify /api/telemetry/stats endpoint returns service metadata and performance statistics."""
    response = client.get("/api/telemetry/stats")
    assert response.status_code == 200
    data = response.json()
    assert data["service_name"] == "pondplan-ai"
    assert "total_requests" in data
    assert "successful_analyses" in data
    assert "recent_spans_count" in data


def test_telemetry_spans_endpoint():
    """Verify /api/telemetry/spans endpoint returns structured OpenTelemetry span history."""
    response = client.get("/api/telemetry/spans")
    assert response.status_code == 200
    data = response.json()
    assert "spans" in data
    assert isinstance(data["spans"], list)


def test_telemetry_logs_endpoint():
    """Verify /api/telemetry/logs endpoint returns structured logs correlated with trace IDs."""
    response = client.get("/api/telemetry/logs")
    assert response.status_code == 200
    data = response.json()
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_trace_id_generation_in_analysis():
    """Verify that analyzing a contour map records OpenTelemetry spans and returns a trace_id."""
    assert os.path.exists(SAMPLE_KML_PATH)
    with open(SAMPLE_KML_PATH, "rb") as f:
        response = client.post(
            "/analyzeContour",
            files={"contour_map": ("contours_1m.kml", f, "application/vnd.google-earth.kml+xml")},
            data={"resolution_m": 15.0},
        )
    assert response.status_code == 200
    data = response.json()
    # Trace ID and Span ID must be present in response
    assert data.get("trace_id") is not None
    assert len(data["trace_id"]) == 32  # 128-bit hex trace ID

    # Check that spans were captured in the in-memory buffer
    spans_resp = client.get("/api/telemetry/spans")
    spans = spans_resp.json()["spans"]
    span_names = [s["name"] for s in spans]
    assert any("kml_parsing" in name for name in span_names)
    assert any("dem_construction" in name for name in span_names)
    assert any("hydrological_terrain_analysis" in name for name in span_names)
