"""DiagnosticResult assembly from the locale catalogue.

[INPUT]
- diagnostics.cooldown_hint::format_cooldown_hint (POS: Cooldown hint rendering for rate-limit diagnostics)
- diagnostics.i18n::get_locale_manager (POS: Framework-level i18n for LLM error diagnostics)
- diagnostics.types::DiagnosticResult (POS: Error diagnostic data structures)

[OUTPUT]
- build_catalog_result: the DiagnosticResult of one catalogue entry (an error type, or a wording variant of it), with
  the provider's wait appended to the message

[POS]
The one place that turns an error type into its localized message and steps, so every diagnostic
family (transport, account, engine) states "which error" and leaves "how it reads" to the catalogue.
"""

from myrm_agent_harness.agent.errors.diagnostics.cooldown_hint import format_cooldown_hint
from myrm_agent_harness.agent.errors.diagnostics.i18n import get_locale_manager
from myrm_agent_harness.agent.errors.diagnostics.types import DiagnosticResult


def build_catalog_result(
    error_type: str,
    locale: str,
    cooldown_remaining_ms: int | None = None,
    *,
    entry: str | None = None,
    **params: object,
) -> DiagnosticResult:
    """The catalogue entry of ``error_type`` rendered in ``locale``; ``params`` fill its placeholders.

    ``entry`` names a wording variant of the same error type, so the result keeps the type its consumers act on.
    """
    locale_manager = get_locale_manager()
    key = entry or error_type
    return DiagnosticResult(
        error_type=error_type,
        user_message=locale_manager.translate(key, "user_message", locale, **params)
        + format_cooldown_hint(cooldown_remaining_ms, locale),
        resolution_steps=locale_manager.translate(key, "resolution_steps", locale, **params),
        locale=locale,
    )
