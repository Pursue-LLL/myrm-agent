"""Permission Engine — wildcard-based rule evaluation for tool-level access control.

[INPUT]
  PermissionRuleset, SecurityConfig, DEFAULT_CAPABILITIES
  approval_reason::ApprovalReasonCode, CodedReason (POS: the unlisted-domain ASK carries a stable code)
  core.security.domain_match::host_matches (POS: one reading of the domain entries of a network list)
  core.security.tool_registry::host_file_paths, url_arg_error, url_arg_hosts (POS: the files a call names, the canonical hosts of the URLs it names, and why a URL has no canonical form)

[OUTPUT]
- evaluate(): resolve action for a (permission, target) pair via last-match-wins
- evaluate_tool_call(): deterministic evaluation (Layers 1–5)
  (capability → shell_command_analyzer → command_denylist → URL scheme check → URL syntax check
   → domain blocklist → domain HITL → path_policy → target-aware ruleset → risk_classifier fallback).
  A URL with no canonical form is denied before any list reads its host; the blocklist and the rule targets
  cover every URL a network tool names; a domain outside the allowlist asks only when the browser navigates there,
  with a CodedReason.
  A command-bearing tool is judged command by command (see command_rules.py) when a
  pattern rule could tell the commands of the line apart.
- check_tool_path_policy(): strictest path-zone verdict over the host files a file tool names (engine and cron policy share it)
- check_capability(): test (permission, target) against a CapabilitySet
- merge(): combine multiple rulesets
- disabled_permissions(): find unconditionally denied permission types
- file_write_disabled(): whether a SecurityConfig unconditionally denies ``file_write``
- extract_url_domains(): the hostnames of a browser navigation, which the person can approve per domain

[POS]
Layers 1–5 of the security architecture. Pure deterministic evaluation —
no side effects, no I/O, trivially testable.
Layer 4.5 (LLM security review) is handled separately in batch_processor.py
since it requires async I/O; this keeps the engine pure.
"""

from __future__ import annotations

from fnmatch import fnmatch

from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode, CodedReason
from myrm_agent_harness.agent.security.command_rules import (
    COMMAND_BEARING_PERMISSIONS,
    check_command_denylist,
    command_text,
    judge_command,
)
from myrm_agent_harness.agent.security.types import (
    DEFAULT_CAPABILITIES,
    CapabilitySet,
    PermissionAction,
    PermissionRule,
    PermissionRuleset,
    SecurityConfig,
)
from myrm_agent_harness.core.security.domain_match import host_matches
from myrm_agent_harness.core.security.tool_registry import host_file_paths, url_arg_error, url_arg_hosts


def _wildcard_match(value: str, pattern: str) -> bool:
    """Match a value against a pattern using fnmatch semantics."""
    if pattern == "*":
        return True
    return fnmatch(value, pattern)


def evaluate(permission: str, target: str, *rulesets: PermissionRuleset) -> PermissionRule:
    """Resolve the effective rule for a (permission, target) pair.

    Uses **last-match-wins** semantics: later rulesets override earlier ones,
    and within a ruleset, later rules override earlier ones. This allows
    user-defined rules to precisely override any default.

    Returns the matching rule, or a fallback ``ASK`` rule if nothing matches.
    """
    merged = merge(*rulesets)
    match: PermissionRule | None = None
    for rule in merged:
        if _wildcard_match(permission, rule.permission) and _wildcard_match(target, rule.pattern):
            match = rule
    return match or PermissionRule(permission, "*", PermissionAction.ASK)


def check_capability(permission: str, target: str, capabilities: CapabilitySet) -> bool:
    """Check if (permission, target) is within the granted capability set.

    Negative capabilities (``!`` prefix) are evaluated first and take
    precedence: if any negative capability matches, the check fails
    immediately regardless of positive grants.
    """
    for cap in capabilities:
        if (
            cap.permission.startswith("!")
            and _wildcard_match(permission, cap.permission[1:])
            and _wildcard_match(target, cap.pattern)
        ):
            return False
    return any(
        not cap.permission.startswith("!")
        and _wildcard_match(permission, cap.permission)
        and _wildcard_match(target, cap.pattern)
        for cap in capabilities
    )


_URL_BEARING_PERMISSIONS: frozenset[str] = frozenset({"web_fetch", "net_fetch", "browser_navigate"})
# Only a browser navigation asks about a domain outside the allowlist: a fetch only reads a page, and is held to the
# blocklist and the ruleset.
_DOMAIN_APPROVAL_PERMISSIONS: frozenset[str] = frozenset({"browser_navigate"})
_PATH_CHECKED_PERMISSIONS: frozenset[str] = frozenset({"file_read", "file_write"})
_ACTION_SEVERITY: dict[PermissionAction, int] = {
    PermissionAction.ALLOW: 0,
    PermissionAction.ASK: 1,
    PermissionAction.DENY: 2,
}


def _check_url_syntax(permission: str, tool_input: dict[str, object]) -> tuple[PermissionAction | None, str]:
    """Deny a URL-bearing tool when a URL it names has no canonical form: no list can judge the host a client would dial."""
    if permission not in _URL_BEARING_PERMISSIONS:
        return None, ""
    error = url_arg_error(tool_input)
    return (PermissionAction.DENY, f"URL not allowed: {error}") if error else (None, "")


def _check_domain_blocklist(
    permission: str, tool_input: dict[str, object], network_blocklist: tuple[str, ...]
) -> tuple[PermissionAction | None, str]:
    """Deny a URL-bearing tool when any host it names matches the network blocklist."""
    if permission not in _URL_BEARING_PERMISSIONS or not network_blocklist:
        return None, ""
    for hostname in url_arg_hosts(tool_input):
        if host_matches(hostname, network_blocklist):
            return PermissionAction.DENY, f"Domain '{hostname}' is blocked by policy"
    return None, ""


def _check_domain_policy(
    permission: str, tool_input: dict[str, object], network_allowlist: tuple[str, ...]
) -> tuple[PermissionAction | None, str]:
    """Ask about a browser navigation to a domain outside the network allowlist (Layer 2c).

    Only applies when ``domain_hitl_enabled`` is True. Callers gate on ``domain_hitl_enabled``.
    """
    if permission not in _DOMAIN_APPROVAL_PERMISSIONS:
        return None, ""
    for hostname in url_arg_hosts(tool_input):
        if not host_matches(hostname, network_allowlist):
            return PermissionAction.ASK, CodedReason(
                f"Domain '{hostname}' requires approval", ApprovalReasonCode.DOMAIN_REQUIRES_APPROVAL, hostname
            )
    return None, ""


def _resolve_target(permission: str, tool_input: dict[str, object], *, tool_name: str | None = None) -> str:
    """Extract the single target resource from tool_input for pattern matching.

    For ``mcp_invoke``, uses the full tool name (e.g. ``mcp__gmail__send_email``)
    as the target, enabling per-tool rules like
    ``{"mcp_invoke": {"mcp__gmail__send_email": "ask", "*": "allow"}}``.
    For ``shell_exec`` and ``code_interpreter`` (the bash tool), uses the command text.
    Returns ``"*"`` for any other permission; the files and URLs a call names are targets of their own
    (see ``_resolve_targets``).
    """
    if permission == "mcp_invoke" and tool_name:
        return tool_name
    if permission in COMMAND_BEARING_PERMISSIONS:
        return command_text(tool_input) or "*"
    return "*"


def _resolve_targets(
    permission: str, tool_input: dict[str, object], *, tool_name: str | None = None
) -> tuple[str, ...]:
    """Every resource a call touches, matched against rules such as ``192.168.*`` or ``*.example.com``.

    Each host file of a file tool and each host of a network tool, whatever the scheme or path of its URL;
    for any other tool the single ``_resolve_target`` target.
    """
    if permission in _PATH_CHECKED_PERMISSIONS:
        return tuple(host_file_paths(tool_input)) or ("*",)
    if permission in _URL_BEARING_PERMISSIONS:
        return url_arg_hosts(tool_input) or ("*",)
    return (_resolve_target(permission, tool_input, tool_name=tool_name),)


def _governing_rule(permission: str, target: str, ruleset: PermissionRuleset, tool_name: str | None) -> PermissionRule:
    """The rule that decides *target*: the last matching rule of the tool's own name, else the last for the permission."""
    if tool_name and tool_name != permission:
        specific: PermissionRule | None = None
        for rule in ruleset:
            if (
                rule.permission != "*"
                and _wildcard_match(tool_name, rule.permission)
                and _wildcard_match(target, rule.pattern)
            ):
                specific = rule
        if specific is not None:
            return specific
    return evaluate(permission, target, ruleset)


def _has_pattern_rules(ruleset: PermissionRuleset, permission: str, tool_name: str | None) -> bool:
    """Whether a rule other than a blanket ``*`` could govern this call, so that the target text matters."""
    names = (permission, tool_name) if tool_name else (permission,)
    return any(
        rule.pattern != "*" and any(_wildcard_match(name, rule.permission) for name in names) for rule in ruleset
    )


def _rule_decision(
    permission: str, target: str, ruleset: PermissionRuleset, tool_name: str | None
) -> tuple[PermissionAction, bool]:
    """The ruleset's action for a call, and whether the read-only classifier may still turn an ASK into an ALLOW.

    Shell tools are judged command by command, but only when a pattern rule could tell commands apart: with
    blanket rules alone the command text cannot change the outcome, so the line is not even split.
    """

    def resolve(text: str) -> PermissionRule:
        return _governing_rule(permission, text, ruleset, tool_name)

    if permission in COMMAND_BEARING_PERMISSIONS and _has_pattern_rules(ruleset, permission, tool_name):
        return judge_command(target, resolve)
    return resolve(target).action, True


def check_tool_path_policy(
    permission: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    workspace_root: str | None,
) -> tuple[PermissionAction, str] | None:
    """Strictest path-zone verdict (session grants included) over the host files a file tool names; ``None`` if it names none."""
    paths = host_file_paths(tool_input) if permission in _PATH_CHECKED_PERMISSIONS else []
    if not paths:
        return None

    from myrm_agent_harness.agent.security.checks import check_path_policy
    from myrm_agent_harness.agent.security.session_access import (
        merge_path_policy_with_session_access,
    )

    policy = merge_path_policy_with_session_access(config.path_policy)
    verdicts = [
        check_path_policy(path, policy, workspace_root, require_write=permission == "file_write") for path in paths
    ]
    return max(verdicts, key=lambda verdict: _ACTION_SEVERITY[verdict[0]])


def evaluate_tool_call(
    permission: str,
    tool_input: dict[str, object],
    config: SecurityConfig,
    *,
    workspace_root: str | None = None,
    tool_name: str | None = None,
) -> tuple[PermissionAction, str]:
    """Top-level entry point: evaluate a tool call against the full security config.

    ``permission`` is the abstract permission type (e.g. ``shell_exec``),
    not the concrete LangChain tool name. Callers must resolve the tool name
    to a permission type via ``tool_registry.resolve_permission_type()``
    before calling this function.

    ``tool_name`` is the original LangChain tool name, passed through for
    target resolution. For ``mcp_invoke`` permission, the tool name
    (e.g. ``mcp__gmail__send_email``) is used as the pattern-matching target,
    enabling per-MCP-tool rules in the permission ruleset.

    Evaluation order:
    1. Capability Fence → not granted → DENY
    2a. Shell Command Analyzer → BLOCK → DENY, ESCALATE → ASK
    2a.5. Command Denylist → user-defined fnmatch globs → DENY (YOLO-proof)
    2b. URL Scheme Check → non-http(s) → DENY
    2b2. Domain Blocklist → any URL of a network tool on the blocklist → DENY
    2c. Domain HITL → browser navigation to a domain not in the allowlist → ASK (when enabled)
    3. Path Policy → forbidden/allowed/workspace check (file_read/file_write only)
    4. Permission ruleset with target resolution → last-match-wins
    5. Risk classifier fallback → SAFE shell commands → ALLOW (shell_exec/code_interpreter)
    6. Fallback → ASK

    Returns (action, reason). Reason is empty for ALLOW.
    """
    from myrm_agent_harness.agent.security.checks import (
        check_navigate_scheme,
        check_shell_threats,
    )

    if not check_capability(permission, "*", config.capabilities):
        return PermissionAction.DENY, f"Capability not granted: {permission}"

    threat_action, threat_reason = check_shell_threats(permission, tool_input)
    if threat_action is not None:
        return threat_action, threat_reason

    deny_action, deny_reason = check_command_denylist(permission, tool_input, config.command_denylist)
    if deny_action is not None:
        return deny_action, deny_reason

    scheme_action, scheme_reason = check_navigate_scheme(permission, tool_input)
    if scheme_action is not None:
        return scheme_action, scheme_reason

    syntax_action, syntax_reason = _check_url_syntax(permission, tool_input)
    if syntax_action is not None:
        return syntax_action, syntax_reason

    block_action, block_reason = _check_domain_blocklist(permission, tool_input, config.network_blocklist)
    if block_action is not None:
        return block_action, block_reason

    decisions = [
        _rule_decision(permission, target, config.ruleset, tool_name)
        for target in _resolve_targets(permission, tool_input, tool_name=tool_name)
    ]
    result_action, classifier_may_allow = max(decisions, key=lambda decision: _ACTION_SEVERITY[decision[0]])

    # Hardline rule: An explicit DENY from user/policy ruleset must never be weakened to ASK
    if result_action == PermissionAction.DENY:
        return (
            PermissionAction.DENY,
            f"Permission '{tool_name or permission}' denied by policy",
        )

    if config.domain_hitl_enabled:
        domain_action, domain_reason = _check_domain_policy(permission, tool_input, config.network_allowlist)
        if domain_action is not None:
            return domain_action, domain_reason

    path_verdict = check_tool_path_policy(permission, tool_input, config, workspace_root)
    if path_verdict is not None and path_verdict[0] in (
        PermissionAction.DENY,
        PermissionAction.ASK,
    ):
        return path_verdict

    if result_action == PermissionAction.ASK and classifier_may_allow and permission in COMMAND_BEARING_PERMISSIONS:
        from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import (
            CommandRiskLevel,
            classify_command_risk,
        )

        command = command_text(tool_input)
        if command and classify_command_risk(command) == CommandRiskLevel.SAFE:
            reason = (
                "Sandbox-aware safe command auto-allow"
                if getattr(config, "is_sandbox", False)
                else "Safe read-only command auto-allow"
            )
            return PermissionAction.ALLOW, reason

    return result_action, ""


def merge(*rulesets: PermissionRuleset) -> PermissionRuleset:
    """Combine multiple rulesets in order (earlier = lower priority)."""
    combined: list[PermissionRule] = []
    for ruleset in rulesets:
        combined.extend(ruleset)
    return tuple(combined)


def disabled_permissions(
    permissions: list[str],
    ruleset: PermissionRuleset,
    capabilities: CapabilitySet = DEFAULT_CAPABILITIES,
) -> frozenset[str]:
    """Return permission types that are unconditionally denied.

    A permission is disabled if:
    - It fails the capability fence (not granted or negatively excluded), OR
    - Its ruleset evaluation yields DENY with pattern ``"*"``

    Useful for stripping denied tools from the LLM tool list before invocation.
    Callers should pass permission types (e.g. ``shell_exec``), not tool names.
    """
    result: set[str] = set()
    for perm in permissions:
        if not check_capability(perm, "*", capabilities):
            result.add(perm)
            continue
        rule = evaluate(perm, "*", ruleset)
        if rule.action == PermissionAction.DENY:
            result.add(perm)
    return frozenset(result)


def file_write_disabled(config: SecurityConfig | None) -> bool:
    """Whether the policy unconditionally denies ``file_write``: a run under it cannot save a file however it asks.

    ``None`` and any object that is not a ``SecurityConfig`` carry no policy to read, so they deny nothing.
    """
    if not isinstance(config, SecurityConfig):
        return False
    return "file_write" in disabled_permissions(["file_write"], config.ruleset, config.capabilities)


def extract_url_domains(permission: str, tool_input: dict[str, object]) -> tuple[str, ...]:
    """The lowercase hostnames the person can approve per domain: those of a browser navigation.

    Empty tuple for any other tool, and when the call names no URL.
    """
    return url_arg_hosts(tool_input) if permission in _DOMAIN_APPROVAL_PERMISSIONS else ()
