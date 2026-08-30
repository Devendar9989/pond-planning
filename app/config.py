"""Application configuration and performance constraints."""

# Default grid resolution in meters
DEFAULT_RESOLUTION_M: float = 10.0

# Memory safety limit on grid cells to guarantee execution within 512MB RAM
MAX_GRID_CELLS: int = 150_000

# Minimum upstream catchment area threshold in square meters
DEFAULT_MIN_CATCHMENT_AREA_M2: float = 500.0

# Maximum file upload size in bytes (25MB)
MAX_UPLOAD_SIZE_BYTES: int = 25 * 1024 * 1024

# Margin cells excluded from being selected as pond outlet
BORDER_CELL_MARGIN: int = 2
