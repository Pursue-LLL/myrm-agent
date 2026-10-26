# metrics/

## Overview
Metrics export and collection. Instruments from `get_meter` are NoOp until `setup_metrics` installs a MeterProvider; export goes through the same OTLP pipeline as tracing (HTTP/protobuf or gRPC, standard environment, shared resource), or to the console for development. Prometheus scraping stays a business-layer concern.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Metrics facade: `setup_metrics`, `get_meter`, `get_metrics_collector`, bounded lifecycle. | ✅ |
| cardinality.py | Core | Metrics cardinality control. Maintains DynamicLabelManager for entity aggregation, and CardinalityFirewall (sanitize_metric_labels) for stripping unbounded high-cardinality keys. | ✅ |
| collector.py | Core | Simplified metrics collection with automatic CardinalityFirewall label sanitization. | ✅ |
| exporter.py | Core | `setup_metrics` on the shared OTLP factory (`OTEL_METRICS_EXPORTER=none` switches metrics off on their own), console export for development, bounded force-flush and shutdown. | ✅ |
| meter.py | Core | Meter provider. Wraps OpenTelemetry Meter acquisition logic. | ✅ |
