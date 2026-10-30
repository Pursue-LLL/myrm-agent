"""Shared types for LLM error diagnostics.

[INPUT]
- (none: standard-library dataclasses only)

[OUTPUT]
- ErrorContext: Model name and endpoint metadata that sharpen a diagnosis
- DiagnosticResult: Localized user message and resolution steps returned to callers

[POS]
Error diagnostic data structures. Frozen dataclasses shared by the diagnostic engine, its
per-family diagnosis modules and the catalogue assembler, so none of them import each other for types.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ErrorContext:
    """Error diagnosis context for custom endpoint and model metadata."""

    model_name: str
    is_custom_endpoint: bool
    base_url: str | None = None


@dataclass(frozen=True)
class DiagnosticResult:
    """Structured LLM error diagnosis returned to callers."""

    error_type: str
    user_message: str
    resolution_steps: list[str]
    locale: str
