"""Unit tests for KML/KMZ parser module."""

import io
import os
import pytest
from app.parser.kml_parser import parse_kml_or_kmz, ContourDataset


SAMPLE_KML_PATH = os.path.join(os.path.dirname(__file__), "..", "contours_1m.kml")


def test_parse_sample_kml():
    """Test parsing the sample contours_1m.kml file."""
    assert os.path.exists(SAMPLE_KML_PATH), "contours_1m.kml must exist in project root"
    dataset = parse_kml_or_kmz(SAMPLE_KML_PATH)

    assert isinstance(dataset, ContourDataset)
    assert len(dataset.lines) > 1000, f"Expected >1000 polylines, got {len(dataset.lines)}"
    assert dataset.elevation_range[0] == pytest.approx(267.0, rel=1e-2)
    assert dataset.elevation_range[1] == pytest.approx(298.0, rel=1e-2)
    assert dataset.contour_interval_m == pytest.approx(1.0, rel=1e-2)

    # Check bounds sanity
    min_lon, min_lat, max_lon, max_lat = dataset.bounds
    assert 81.0 < min_lon < 82.0
    assert 21.0 < min_lat < 22.0
    assert max_lon > min_lon
    assert max_lat > min_lat


def test_parse_empty_kml():
    """Test error handling for empty file content."""
    with pytest.raises(ValueError, match="empty"):
        parse_kml_or_kmz(b"")


def test_parse_invalid_kml():
    """Test error handling for invalid XML."""
    with pytest.raises(ValueError):
        parse_kml_or_kmz(b"This is not XML at all!")


def test_parse_kml_without_placemarks():
    """Test error handling when no placemarks are present."""
    empty_kml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <kml xmlns="http://www.opengis.net/kml/2.2">
      <Document>
        <name>Empty</name>
      </Document>
    </kml>"""
    with pytest.raises(ValueError, match="No Placemarks"):
        parse_kml_or_kmz(empty_kml)
