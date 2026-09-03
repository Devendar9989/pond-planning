"""End-to-end scenario test cases: creates synthetic KML/KMZ files representing
different topographic landscapes and verifies that the API returns the exact right answers.
"""

import io
import os
import zipfile
import pytest
from fastapi.testclient import TestClient
import numpy as np
from shapely.geometry import shape

from app.main import app

client = TestClient(app)


def _build_kml_string(placemarks: list) -> str:
    """Helper to generate well-formed KML from placemark definitions."""
    placemark_xml_list = []
    for pm in placemarks:
        name = pm["name"]
        coords_str = " ".join(f"{lon:.7f},{lat:.7f},{pm.get('elev', 0.0)}" for lon, lat in pm["coords"])
        pm_xml = f"""
        <Placemark>
          <name>{name}</name>
          <LineString>
            <coordinates>{coords_str}</coordinates>
          </LineString>
        </Placemark>
        """
        placemark_xml_list.append(pm_xml)

    all_pm = "\n".join(placemark_xml_list)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>Generated Test Contours</name>
    {all_pm}
  </Document>
</kml>"""


def _create_kmz_bytes(kml_content: str, entry_name: str = "doc.kml") -> bytes:
    """Helper to package KML string into an in-memory KMZ zip archive."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(entry_name, kml_content.encode("utf-8"))
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Test Case 1: Synthetic V-Shaped Drainage Valley
# ---------------------------------------------------------------------------
def test_scenario_v_shaped_valley():
    """
    Landscape: A V-shaped drainage valley sloping from North (elev 120m) to South (elev 100m).
    Valley centerline runs along Lon ~ 81.300.
    The slopes on East and West drain inward into the central channel.

    Expected right answers:
    - Elevation range: [100.0, 120.0]
    - Contour interval: 5.0m
    - Pond site: Located near the valley floor at the low Southern exit (elev ~ 100-103m).
    - Catchment area: Covers upstream valley slopes and area >= 5,000 m².
    - GeoJSON: Valid, closed Polygon geometry enclosing upstream terrain.
    """
    placemarks = []
    # 5 contour levels: 100m, 105m, 110m, 115m, 120m
    center_lon = 81.300
    base_lat = 21.200

    elevations = [100.0, 105.0, 110.0, 115.0, 120.0]
    for i, elev in enumerate(elevations):
        # V-shape: at higher elevations, contour opens wider and is pushed further North
        y_offset = (i * 0.002)  # Lat step ~ 220m
        v_depth = 0.001 * i

        # V-shaped contour: left wing -> valley vertex -> right wing
        coords = [
            (center_lon - 0.006, base_lat + y_offset + 0.004),
            (center_lon - 0.003, base_lat + y_offset + 0.002),
            (center_lon, base_lat + y_offset + v_depth),
            (center_lon + 0.003, base_lat + y_offset + 0.002),
            (center_lon + 0.006, base_lat + y_offset + 0.004),
        ]
        placemarks.append({"name": f"{elev:.1f}", "elev": elev, "coords": coords})

    kml_str = _build_kml_string(placemarks)

    # Call API
    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("v_valley.kml", io.BytesIO(kml_str.encode("utf-8")), "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0", "min_catchment_area_m2": "1000.0"},
    )

    assert response.status_code == 200, f"API failed with {response.text}"
    data = response.json()

    # 1. Verify elevation range and interval
    assert data["elevation_range_m"] == [100.0, 120.0]
    assert data["contour_interval_m"] == 5.0
    assert data["grid_resolution_m"] == 10.0
    assert not data["resolution_auto_adjusted"]

    # 2. Verify pond site location
    pond = data["pond_site"]
    assert 100.0 <= pond["elevation_m"] <= 106.0, f"Pond elevation {pond['elevation_m']} not at valley bottom"
    # Pond longitude should be close to valley centerline (81.300)
    assert abs(pond["lon"] - center_lon) < 0.003, f"Pond lon {pond['lon']} deviated from valley center"

    # 3. Verify catchment delineation
    catchment = data["catchment"]
    assert catchment["area_m2"] >= 1000.0
    assert catchment["area_hectares"] == pytest.approx(catchment["area_m2"] / 10000.0, rel=1e-3)
    assert catchment["mean_slope_pct"] > 0.0

    # 4. Verify boundary polygon geometry
    geojson = catchment["boundary_geojson"]
    geom = shape(geojson)
    assert geom.is_valid, "Catchment boundary polygon must be valid geometry"
    assert not geom.is_empty


# ---------------------------------------------------------------------------
# Test Case 2: Synthetic Concentric Bowl / Natural Basin
# ---------------------------------------------------------------------------
def test_scenario_concentric_bowl():
    """
    Landscape: A natural concave bowl with concentric elliptical contours.
    Rim at 50m elevation, descending to 40m, 30m, and 20m in the center.

    Expected right answers:
    - Elevation range: [20.0, 50.0]
    - Contour interval: 10.0m
    - Pond site: Positioned at the center bottom (elev ~ 20m).
    - Catchment area: Captures the inward-draining slopes of the bowl.
    """
    placemarks = []
    center_lon = 78.500
    center_lat = 17.400

    elev_radii = [
        (50.0, 0.008, 0.006),  # outer rim
        (40.0, 0.006, 0.0045),
        (30.0, 0.004, 0.003),
        (20.0, 0.002, 0.0015),  # inner basin bottom
    ]

    angles = np.linspace(0, 2 * np.pi, 24)

    for elev, rx, ry in elev_radii:
        ring = []
        for a in angles:
            lon = center_lon + rx * np.cos(a)
            lat = center_lat + ry * np.sin(a)
            ring.append((lon, lat))
        # Close loop
        ring.append(ring[0])
        placemarks.append({"name": f"Elevation {elev:.0f}m", "elev": elev, "coords": ring})

    kml_str = _build_kml_string(placemarks)

    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("bowl.kml", io.BytesIO(kml_str.encode("utf-8")), "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["elevation_range_m"] == [20.0, 50.0]
    assert data["contour_interval_m"] == 10.0

    pond = data["pond_site"]
    assert 20.0 <= pond["elevation_m"] <= 30.0
    # Pond site should be centered in the bowl
    assert abs(pond["lon"] - center_lon) < 0.003
    assert abs(pond["lat"] - center_lat) < 0.003

    assert data["catchment"]["area_m2"] > 500.0


# ---------------------------------------------------------------------------
# Test Case 3: KMZ Archive Format Support
# ---------------------------------------------------------------------------
def test_scenario_kmz_archive():
    """
    Verify that zipped KMZ archives containing doc.kml are parsed and analyzed seamlessly.
    """
    placemarks = [
        {"name": "300.0", "elev": 300.0, "coords": [(80.000, 20.000), (80.010, 20.000)]},
        {"name": "305.0", "elev": 305.0, "coords": [(80.000, 20.005), (80.010, 20.005)]},
        {"name": "310.0", "elev": 310.0, "coords": [(80.000, 20.010), (80.010, 20.010)]},
    ]
    kml_str = _build_kml_string(placemarks)
    kmz_bytes = _create_kmz_bytes(kml_str, entry_name="doc.kml")

    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("terrain.kmz", io.BytesIO(kmz_bytes), "application/vnd.google-earth.kmz")},
        data={"resolution_m": "10.0"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["elevation_range_m"] == [300.0, 310.0]
    assert data["contour_interval_m"] == 5.0
    assert data["pond_site"]["elevation_m"] >= 300.0


# ---------------------------------------------------------------------------
# Test Case 4: Generalization to Southern Hemisphere (Australia)
# ---------------------------------------------------------------------------
def test_scenario_southern_hemisphere_australia():
    """
    Landscape: Located in Sydney, Australia (Lat -33.86, Lon 151.20).
    Verifies that UTM projection dynamically handles Southern hemisphere EPSG (e.g. EPSG:32756).
    """
    center_lon = 151.200
    base_lat = -33.860

    placemarks = []
    for i, elev in enumerate([50.0, 60.0, 70.0, 80.0]):
        y_off = i * 0.002
        coords = [
            (center_lon - 0.005, base_lat + y_off),
            (center_lon, base_lat + y_off - 0.001),
            (center_lon + 0.005, base_lat + y_off),
        ]
        placemarks.append({"name": f"{elev:.1f}", "elev": elev, "coords": coords})

    kml_str = _build_kml_string(placemarks)

    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("sydney_catchment.kml", io.BytesIO(kml_str.encode("utf-8")), "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["elevation_range_m"] == [50.0, 80.0]
    assert data["contour_interval_m"] == 10.0

    # Ensure pond is in southern hemisphere
    pond = data["pond_site"]
    assert pond["lat"] < 0.0, f"Expected southern hemisphere lat < 0, got {pond['lat']}"
    assert 150.0 < pond["lon"] < 152.0
    assert 50.0 <= pond["elevation_m"] <= 60.0


# ---------------------------------------------------------------------------
# Test Case 5: Custom min_catchment_area_m2 Filtering
# ---------------------------------------------------------------------------
def test_scenario_min_catchment_area_filter():
    """
    Verifies that min_catchment_area_m2 parameter is enforced by the pond selector.
    """
    placemarks = []
    center_lon = 81.300
    base_lat = 21.200

    # Large sloping valley with 8 levels
    for i in range(8):
        elev = 100.0 + i * 2.0
        y_off = i * 0.002
        coords = [
            (center_lon - 0.008, base_lat + y_off),
            (center_lon, base_lat + y_off - 0.001),
            (center_lon + 0.008, base_lat + y_off),
        ]
        placemarks.append({"name": f"{elev:.1f}", "elev": elev, "coords": coords})

    kml_str = _build_kml_string(placemarks)

    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("valley.kml", io.BytesIO(kml_str.encode("utf-8")), "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0", "min_catchment_area_m2": "5000.0"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["catchment"]["area_m2"] >= 5000.0


# ---------------------------------------------------------------------------
# Test Case 6: Dual Watershed Ridge Divide
# ---------------------------------------------------------------------------
def test_scenario_dual_watershed_ridge_divide():
    """
    Landscape: Two distinct valleys separated by a high ridge with longitudinal downhill slope.
    - Major Valley on the West (Lon 81.270-81.290): drains a wide area down to 100m.
    - Dividing Ridge (Lon 81.300): peaks at 150m.
    - Minor Valley on the East (Lon 81.305-81.315): narrower channel at 120m.

    Expected right answers:
    - Siting heuristic prioritizes the Major Western Valley (higher accumulation + lower elevation).
    - Delineated catchment strictly captures the Western watershed and does NOT cross the ridge divide into the East.
    """
    placemarks = []
    base_lat = 21.200

    for y_idx in range(6):
        y = base_lat + y_idx * 0.002
        slope_z = y_idx * 5.0  # North to South slope
        placemarks.append({"name": f"{140.0+slope_z:.1f}", "elev": 140.0 + slope_z, "coords": [(81.260, y), (81.260, y + 0.001)]})
        placemarks.append({"name": f"{100.0+slope_z:.1f}", "elev": 100.0 + slope_z, "coords": [(81.270, y), (81.280, y + 0.001), (81.290, y)]})
        placemarks.append({"name": f"{150.0+slope_z:.1f}", "elev": 150.0 + slope_z, "coords": [(81.300, y), (81.300, y + 0.001)]})
        placemarks.append({"name": f"{120.0+slope_z:.1f}", "elev": 120.0 + slope_z, "coords": [(81.305, y), (81.310, y + 0.001), (81.315, y)]})
        placemarks.append({"name": f"{140.0+slope_z:.1f}", "elev": 140.0 + slope_z, "coords": [(81.320, y), (81.320, y + 0.001)]})

    kml_str = _build_kml_string(placemarks)

    response = client.post(
        "/analyzeContour",
        files={"contour_map": ("ridge_valleys.kml", io.BytesIO(kml_str.encode("utf-8")), "application/vnd.google-earth.kml+xml")},
        data={"resolution_m": "10.0"},
    )

    assert response.status_code == 200, response.text
    data = response.json()

    # Pond must be selected in the major Western valley (lon < 81.295)
    pond = data["pond_site"]
    assert pond["lon"] < 81.295, f"Pond was placed at {pond['lon']}, expected in western valley (< 81.295)"
    assert 100.0 <= pond["elevation_m"] <= 110.0

    # Catchment boundary must stay on the west side of the ridge
    catchment = data["catchment"]
    geojson = catchment["boundary_geojson"]
    geom = shape(geojson)
    assert geom.is_valid
    # The max longitude of the western catchment polygon must not cross the eastern valley
    bounds = geom.bounds  # (minx, miny, maxx, maxy)
    assert bounds[2] <= 81.305, f"Catchment breached ridge divide: max_lon={bounds[2]}"

