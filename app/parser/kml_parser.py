"""Robust, namespace-agnostic parser for KML and KMZ contour map files."""

from dataclasses import dataclass
import io
import re
from typing import BinaryIO, List, Optional, Tuple, Union
import zipfile
from lxml import etree
import numpy as np


@dataclass
class ContourLine:
    """Represents a single contour polyline with its elevation."""
    elevation: float
    # Coordinates in WGS84 (longitude, latitude)
    coords: List[Tuple[float, float]]


@dataclass
class ContourDataset:
    """Collection of contour lines with extracted metadata."""
    lines: List[ContourLine]
    total_contour_lines: int
    elevation_range: Tuple[float, float]
    contour_interval_m: float
    bounds: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    centroid: Tuple[float, float]  # (center_lon, center_lat)


def _extract_elevation_from_text(text: Optional[str]) -> Optional[float]:
    """Attempts to extract a float elevation value from a string."""
    if not text:
        return None
    text = text.strip()
    try:
        return float(text)
    except ValueError:
        pass
    # Try finding numeric values like 'Contour 270m' or '270.5'
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if match:
        try:
            return float(match.group(0))
        except ValueError:
            return None
    return None


def _extract_elevation_from_element(placemark: etree._Element) -> Optional[float]:
    """Extracts elevation from Placemark name, description, or ExtendedData."""
    # 1. Check <name>
    for name_elem in placemark.xpath('.//*[local-name()="name"]'):
        elev = _extract_elevation_from_text(name_elem.text)
        if elev is not None:
            return elev

    # 2. Check <ExtendedData> / <SimpleData>
    for simple_data in placemark.xpath('.//*[local-name()="SimpleData"]'):
        attr_name = simple_data.attrib.get("name", "").lower()
        if any(keyword in attr_name for keyword in ("elev", "contour", "height", "z", "alt")):
            elev = _extract_elevation_from_text(simple_data.text)
            if elev is not None:
                return elev

    # 3. Check <description>
    for desc_elem in placemark.xpath('.//*[local-name()="description"]'):
        elev = _extract_elevation_from_text(desc_elem.text)
        if elev is not None:
            return elev

    return None


def _parse_coordinates_text(coord_text: str) -> List[Tuple[float, float]]:
    """Parses whitespace-separated lon,lat[,z] tuples into a list of (lon, lat)."""
    coords: List[Tuple[float, float]] = []
    # KML coordinates are typically space/newline separated triplets: lon,lat,alt
    raw_tuples = coord_text.strip().split()
    for item in raw_tuples:
        parts = item.split(",")
        if len(parts) >= 2:
            try:
                lon = float(parts[0].strip())
                lat = float(parts[1].strip())
                coords.append((lon, lat))
            except ValueError:
                continue
    return coords


def _read_kml_bytes(source: Union[str, bytes, BinaryIO]) -> bytes:
    """Reads raw KML bytes, unpacking KMZ if necessary."""
    raw_bytes: bytes
    if isinstance(source, bytes):
        raw_bytes = source
    elif isinstance(source, str):
        with open(source, "rb") as f:
            raw_bytes = f.read()
    else:
        raw_bytes = source.read()

    # Check if the stream is a ZIP file (KMZ archive)
    if zipfile.is_zipfile(io.BytesIO(raw_bytes)):
        with zipfile.ZipFile(io.BytesIO(raw_bytes), "r") as z:
            # Find the main .kml file inside
            kml_filenames = [name for name in z.namelist() if name.lower().endswith(".kml")]
            if not kml_filenames:
                raise ValueError("KMZ archive does not contain any .kml files.")
            # Standard KMZ convention uses doc.kml or the first .kml file
            target_kml = "doc.kml" if "doc.kml" in kml_filenames else kml_filenames[0]
            raw_bytes = z.read(target_kml)

    return raw_bytes


def parse_kml_or_kmz(source: Union[str, bytes, BinaryIO]) -> ContourDataset:
    """
    Parses a KML or KMZ file and extracts contour polylines and metadata.

    Args:
        source: File path, raw bytes, or file-like binary stream.

    Returns:
        ContourDataset containing all extracted contour polylines and statistics.

    Raises:
        ValueError: If file is invalid XML or contains no contour lines.
    """
    kml_bytes = _read_kml_bytes(source)
    if not kml_bytes.strip():
        raise ValueError("Provided KML file is empty.")

    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        root = etree.fromstring(kml_bytes, parser=parser)
        if root is None:
            raise ValueError("Failed to parse KML XML: Document is empty or invalid.")
    except Exception as e:
        raise ValueError(f"Failed to parse KML XML structure: {e}")

    placemarks = root.xpath('.//*[local-name()="Placemark"]')
    if not placemarks:
        raise ValueError("No Placemarks found in KML file.")

    contour_lines: List[ContourLine] = []
    all_lons: List[float] = []
    all_lats: List[float] = []
    unique_elevations = set()

    total_contour_features = 0

    for pm in placemarks:
        elevation = _extract_elevation_from_element(pm)
        if elevation is None:
            continue

        # Extract coordinates from all <coordinates> elements within this placemark
        coord_elements = pm.xpath('.//*[local-name()="coordinates"]')
        for ce in coord_elements:
            if not ce.text:
                continue
            coords = _parse_coordinates_text(ce.text)
            if len(coords) >= 1:
                total_contour_features += 1
            if len(coords) >= 2:  # Must have at least 2 points to form a segment
                contour_lines.append(ContourLine(elevation=elevation, coords=coords))
                unique_elevations.add(elevation)
                for lon, lat in coords:
                    all_lons.append(lon)
                    all_lats.append(lat)

    if not contour_lines:
        raise ValueError("No valid contour polylines with elevations found in KML file.")

    elev_sorted = sorted(unique_elevations)
    min_elev = float(elev_sorted[0])
    max_elev = float(elev_sorted[-1])

    # Compute contour interval dynamically from difference between sorted elevation levels
    if len(elev_sorted) > 1:
        diffs = np.diff(elev_sorted)
        # Filter out 0 or negative diffs if any
        positive_diffs = diffs[diffs > 0.001]
        contour_interval = float(np.median(positive_diffs)) if len(positive_diffs) > 0 else 1.0
    else:
        contour_interval = 1.0

    min_lon = float(min(all_lons))
    max_lon = float(max(all_lons))
    min_lat = float(min(all_lats))
    max_lat = float(max(all_lats))

    dataset = ContourDataset(
        lines=contour_lines,
        total_contour_lines=total_contour_features,
        elevation_range=(min_elev, max_elev),
        contour_interval_m=round(contour_interval, 2),
        bounds=(min_lon, min_lat, max_lon, max_lat),
        centroid=((min_lon + max_lon) / 2.0, (min_lat + max_lat) / 2.0),
    )
    return dataset
