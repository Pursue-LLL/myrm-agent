# dataset_export/

## Overview
Export pipeline — convert ExecutionTrace into standard fine-tuning datasets (ShareGPT / Alpaca / OpenAI JSONL) with credential masking, PII redaction, quality filtering, content deduplication, and incremental export support.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Re-exports DatasetExporter, ExportConfig, ExportFormat, ExportReport | ✅ |
| protocols.py | Config | ExportFormat, ExportConfig, QualityThresholds, ExportReport type definitions | ✅ |
| quality_filter.py | Core | 3-dimension quality gate (task outcome, conversation depth, content integrity) | ✅ |
| format_converter.py | Core | 3-format conversion (ShareGPT/Alpaca/OpenAI), SHA-256 dedup, credential masking (`redact_trace_credentials`: the task input, the output and every tool call's arguments, output summary and error; always applied, since a dataset has no use for a credential and the event log keeps tool arguments as the tool saw them), PII redaction | ✅ |
| exporter.py | Core | DatasetExporter async orchestrator — streams traces, writes JSONL, tracks incremental state | ✅ |

## Key Dependencies

- `event_log.trace_builder` — build_trace for trace construction
- `event_log.protocols` — EventLogBackend protocol
- `core.security.redact` — `redact_nested`, `redact_field_text` and `redact_sensitive_text` for credential masking
- `security.detection.pii_redactor` — redact_pii for PII masking
