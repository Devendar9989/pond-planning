"""
OpenTelemetry instrumentation and observability module for PondPlan AI.
Provides:
1. Distributed Tracing with OpenTelemetry SDK & OTLP Exporter (Jaeger / OTel Collector).
2. Metrics with OpenTelemetry Meter & Prometheus Exporter (/metrics).
3. Structured Logging correlated with active Trace ID and Span ID.
4. In-Memory Trace, Log, and Metrics Buffers for embedded Live Observability Dashboard.
"""

from collections import deque
from contextlib import contextmanager
import datetime
import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional

# OpenTelemetry Tracing
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor
from opentelemetry.trace import Status, StatusCode

# OpenTelemetry Metrics
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

# Prometheus Client
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Setup Logging
logger = logging.getLogger("pondplan.telemetry")

# ---------------------------------------------------------------------------
# In-Memory Ring Buffers for Live Frontend Observability
# ---------------------------------------------------------------------------
MAX_SPANS_BUFFER = 100
MAX_LOGS_BUFFER = 200

_recent_spans: deque = deque(maxlen=MAX_SPANS_BUFFER)
_recent_logs: deque = deque(maxlen=MAX_LOGS_BUFFER)
_telemetry_lock = threading.Lock()

# Summary Metrics for API & Frontend
_telemetry_stats = {
    "service_name": "pondplan-ai",
    "environment": os.getenv("APP_ENV", "production"),
    "start_time": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    "total_requests": 0,
    "successful_analyses": 0,
    "failed_analyses": 0,
    "active_requests": 0,
    "total_processing_time_ms": 0.0,
    "avg_processing_time_ms": 0.0,
    "last_trace_id": None,
    "last_analysis": None,
}


# ---------------------------------------------------------------------------
# Custom Span Processor to capture spans in memory for the UI
# ---------------------------------------------------------------------------
class InMemorySpanBufferProcessor(SpanProcessor):
    """Custom OpenTelemetry SpanProcessor that buffers completed spans for inspection."""

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span: ReadableSpan):
        try:
            ctx = span.get_span_context()
            trace_id = format(ctx.trace_id, "032x") if ctx.trace_id else None
            span_id = format(ctx.span_id, "016x") if ctx.span_id else None
            parent_id = format(span.parent.span_id, "016x") if span.parent and span.parent.span_id else None

            duration_ms = 0.0
            if span.end_time and span.start_time:
                duration_ms = round((span.end_time - span.start_time) / 1_000_000, 2)

            attributes = {}
            if span.attributes:
                for k, v in span.attributes.items():
                    attributes[k] = str(v) if not isinstance(v, (int, float, bool)) else v

            events_list = []
            if span.events:
                for ev in span.events:
                    events_list.append({
                        "name": ev.name,
                        "timestamp": ev.timestamp,
                        "attributes": dict(ev.attributes) if ev.attributes else {},
                    })

            span_data = {
                "name": span.name,
                "trace_id": trace_id,
                "span_id": span_id,
                "parent_span_id": parent_id,
                "duration_ms": duration_ms,
                "status": span.status.status_code.name if span.status else "UNSET",
                "status_description": span.status.description if span.status else None,
                "start_time": datetime.datetime.fromtimestamp(
                    span.start_time / 1_000_000_000, tz=datetime.timezone.utc
                ).isoformat() if span.start_time else None,
                "attributes": attributes,
                "events": events_list,
            }

            with _telemetry_lock:
                _recent_spans.appendleft(span_data)
                if trace_id:
                    _telemetry_stats["last_trace_id"] = trace_id

        except Exception as e:
            logger.debug(f"Failed to buffer span in memory: {e}")

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


# ---------------------------------------------------------------------------
# Custom Logging Handler to capture correlated logs in memory
# ---------------------------------------------------------------------------
class OTelLogBufferHandler(logging.Handler):
    """Logging handler that captures logs correlated with active OpenTelemetry trace/span IDs."""

    def emit(self, record: logging.LogRecord):
        try:
            current_span = trace.get_current_span()
            ctx = current_span.get_span_context() if current_span else None
            trace_id = format(ctx.trace_id, "032x") if ctx and ctx.trace_id else None
            span_id = format(ctx.span_id, "016x") if ctx and ctx.span_id else None

            log_entry = {
                "timestamp": datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "trace_id": trace_id,
                "span_id": span_id,
                "line": record.lineno,
                "filename": record.filename,
            }

            with _telemetry_lock:
                _recent_logs.appendleft(log_entry)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Prometheus Direct Metric Instruments
# ---------------------------------------------------------------------------
PROM_REQUESTS_TOTAL = Counter(
    "pondplan_requests_total",
    "Total HTTP requests received",
    ["method", "endpoint", "status_code"],
)

PROM_ANALYSIS_DURATION = Histogram(
    "pondplan_analysis_duration_seconds",
    "Total duration of contour analysis in seconds",
    buckets=[0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0],
)

PROM_STAGE_DURATION = Histogram(
    "pondplan_stage_duration_seconds",
    "Duration of individual hydrological analysis stages",
    ["stage"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.0, 5.0],
)

PROM_CATCHMENT_AREA = Gauge(
    "pondplan_catchment_area_m2",
    "Calculated upstream catchment area in square meters",
)

PROM_WATER_VOLUME = Gauge(
    "pondplan_expected_water_volume_m3",
    "Calculated annual harvestable water volume in cubic meters",
)

PROM_GRID_CELLS = Gauge(
    "pondplan_dem_grid_cells_total",
    "Total number of grid cells in the reconstructed DEM",
)

PROM_ACTIVE_REQUESTS = Gauge(
    "pondplan_active_analyses",
    "Currently in-progress contour analyses",
)


# ---------------------------------------------------------------------------
# OpenTelemetry Tracer & Meter Initialization
# ---------------------------------------------------------------------------
_tracer = None
_meter = None


def setup_telemetry(service_name: str = "pondplan-ai") -> trace.Tracer:
    """Configures and initializes OpenTelemetry Tracing, Metrics, and Log handlers."""
    global _tracer, _meter

    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.0.0",
        "deployment.environment": os.getenv("APP_ENV", "production"),
        "host.name": os.uname().nodename if hasattr(os, "uname") else "local",
        "service.namespace": "iitbhilai.csd",
    })

    # Tracer Provider
    provider = TracerProvider(resource=resource)

    # 1. In-Memory Span Processor (always active for UI and local diagnostics)
    provider.add_span_processor(InMemorySpanBufferProcessor())

    # 2. OTLP HTTP Exporter (Jaeger / OpenTelemetry Collector endpoint)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4318/v1/traces")
    enable_otlp = os.getenv("OTEL_EXPORTER_ENABLED", "auto").lower()

    should_export_otlp = False
    if enable_otlp in ("true", "1", "yes"):
        should_export_otlp = True
    elif enable_otlp == "auto":
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.2)
            res = s.connect_ex(("127.0.0.1", 4318))
            s.close()
            should_export_otlp = (res == 0)
        except Exception:
            should_export_otlp = False

    if should_export_otlp:
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, timeout=2)
            provider.add_span_processor(
                BatchSpanProcessor(otlp_exporter, max_queue_size=512, schedule_delay_millis=500)
            )
            logger.info(f"OpenTelemetry OTLP Span Exporter registered to {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"Could not initialize OTLP Span Exporter: {e}")
    else:
        logger.info("OTLP remote exporter skipped (no local OTLP collector listening on 4318).")

    trace.set_tracer_provider(provider)
    _tracer = trace.get_tracer(service_name, "1.0.0")

    # Meter Provider
    meter_provider = MeterProvider(resource=resource)
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(service_name, "1.0.0")

    # Setup Logging Handler for Trace Correlation
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    buffer_handler = OTelLogBufferHandler()
    buffer_handler.setLevel(logging.INFO)
    root_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [trace_id=%(otelTraceID)s span_id=%(otelSpanID)s] %(name)s: %(message)s",
        defaults={"otelTraceID": "0" * 32, "otelSpanID": "0" * 16},
    )
    buffer_handler.setFormatter(root_formatter)
    root_logger.addHandler(buffer_handler)

    app_logger = logging.getLogger("pondplan-ai")
    app_logger.setLevel(logging.INFO)
    app_logger.addHandler(buffer_handler)

    logger.info("OpenTelemetry Tracing and Metrics initialized successfully.")
    return _tracer


def flush_telemetry(timeout_millis: int = 2000):
    """Force flushes all active span processors to ensure instant delivery to Jaeger."""
    try:
        provider = trace.get_tracer_provider()
        if provider and hasattr(provider, "force_flush"):
            provider.force_flush(timeout_millis)
    except Exception as e:
        logger.debug(f"Telemetry flush exception: {e}")


def get_tracer() -> trace.Tracer:
    """Returns the active OpenTelemetry tracer."""
    global _tracer
    if _tracer is None:
        _tracer = setup_telemetry()
    return _tracer


# ---------------------------------------------------------------------------
# Convenient Tracing Context Manager
# ---------------------------------------------------------------------------
@contextmanager
def trace_stage(stage_name: str, attributes: Optional[Dict[str, Any]] = None):
    """
    Context manager to trace a hydrological processing stage as an OpenTelemetry Span.
    Measures duration, records attributes, catches exceptions, and updates Prometheus metrics.
    """
    tracer = get_tracer()
    start_t = time.perf_counter()

    with tracer.start_as_current_span(stage_name) as span:
        if attributes:
            for k, v in attributes.items():
                if v is not None:
                    span.set_attribute(k, v)

        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            logger.error(f"Error in stage {stage_name}: {exc}", exc_info=True)
            raise
        finally:
            elapsed = time.perf_counter() - start_t
            span.set_attribute("duration_ms", round(elapsed * 1000, 2))
            try:
                PROM_STAGE_DURATION.labels(stage=stage_name).observe(elapsed)
            except Exception:
                pass


# ---------------------------------------------------------------------------
# API Query Functions for Observability Data
# ---------------------------------------------------------------------------
def record_analysis_metrics(
    catchment_area_m2: float,
    water_volume_m3: float,
    grid_cells: int,
    duration_s: float,
    elevation_min: float,
    elevation_max: float,
    trace_id: Optional[str] = None,
):
    """Updates Prometheus gauges and in-memory statistics after an analysis completes."""
    with _telemetry_lock:
        _telemetry_stats["total_requests"] += 1
        _telemetry_stats["successful_analyses"] += 1
        _telemetry_stats["total_processing_time_ms"] += duration_s * 1000
        _telemetry_stats["avg_processing_time_ms"] = round(
            _telemetry_stats["total_processing_time_ms"] / _telemetry_stats["successful_analyses"], 2
        )
        if trace_id:
            _telemetry_stats["last_trace_id"] = trace_id

        _telemetry_stats["last_analysis"] = {
            "catchment_area_m2": catchment_area_m2,
            "catchment_area_ha": round(catchment_area_m2 / 10000.0, 2),
            "expected_water_volume_m3": round(water_volume_m3, 2),
            "expected_water_volume_ml": round(water_volume_m3 / 1000.0, 2),
            "grid_cells": grid_cells,
            "duration_ms": round(duration_s * 1000, 2),
            "elevation_range_m": [elevation_min, elevation_max],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "trace_id": trace_id,
        }

    # Update Prometheus
    PROM_CATCHMENT_AREA.set(catchment_area_m2)
    PROM_WATER_VOLUME.set(water_volume_m3)
    PROM_GRID_CELLS.set(grid_cells)
    PROM_ANALYSIS_DURATION.observe(duration_s)


def record_analysis_failure():
    """Records a failed analysis attempt."""
    with _telemetry_lock:
        _telemetry_stats["total_requests"] += 1
        _telemetry_stats["failed_analyses"] += 1


def get_recent_spans() -> List[Dict[str, Any]]:
    """Returns the buffered list of recent OpenTelemetry spans."""
    with _telemetry_lock:
        return list(_recent_spans)


def get_recent_logs() -> List[Dict[str, Any]]:
    """Returns the buffered list of recent correlated logs."""
    with _telemetry_lock:
        return list(_recent_logs)


def get_telemetry_stats() -> Dict[str, Any]:
    """Returns overall telemetry and performance metrics."""
    with _telemetry_lock:
        stats = dict(_telemetry_stats)
        stats["recent_spans_count"] = len(_recent_spans)
        stats["recent_logs_count"] = len(_recent_logs)
        return stats


def get_prometheus_metrics_bytes() -> bytes:
    """Generates standard Prometheus plaintext exposition format."""
    return generate_latest()
