"""Taint Tracker — session-level information-flow tracking for tool outputs.

Tracks which tool categories have produced output in the current session,
and checks whether a tool call is safe given the accumulated taint labels.

Since the LLM is a black box, taint propagation is approximate: once a
tool produces tainted output, all subsequent tool calls to incompatible
sinks are escalated to ASK (require user approval) rather than blocked.

[INPUT]
- agent.security.command_rules::command_text (POS: the text a command-bearing tool runs: the one field of its input the tool executes)
- core.security.domain_match::host_matches (POS: one reading of the domain entries of a network list)
- core.security.tool_registry::URL_BEARING_PERMISSIONS, resolve_permission_type, url_arg_hosts (POS: the tools that take URLs, the permission type of a call, and the hosts of the URLs a call names under every argument spelling)

[OUTPUT]
- TaintLabel: source categories (EXTERNAL_NETWORK, SECRET, PII_SENSITIVE, UNTRUSTED_INGRESS)
- TaintTracker: session-level taint accumulator
- TAINT_SINK_POLICIES: sink tool name (a tool, never a permission type) → set of blocked TaintLabels
- get_taint_tracker() / reset_taint_tracker(): ContextVar accessors

[POS]
Layer 2 enhancement. Sits between tool_interceptor (records taint after
tool execution) and tool_approval (checks taint before tool execution).
Prevents the classic prompt-injection → command-injection attack chain
by escalating suspicious tool calls to user approval.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Collection
from contextvars import ContextVar
from enum import StrEnum, unique

from myrm_agent_harness.agent.security.command_rules import command_text
from myrm_agent_harness.core.security.domain_match import host_matches
from myrm_agent_harness.core.security.tool_registry import (
    URL_BEARING_PERMISSIONS,
    resolve_permission_type,
    url_arg_hosts,
)

logger = logging.getLogger(__name__)


@unique
class TaintLabel(StrEnum):
    """Categories of tainted data flowing through the session."""

    EXTERNAL_NETWORK = "external_network"
    SECRET = "secret"
    PII_SENSITIVE = "pii_sensitive"
    UNTRUSTED_INGRESS = "untrusted_ingress"


TAINT_SINK_POLICIES: dict[str, frozenset[TaintLabel]] = {
    "bash_code_execute_tool": frozenset({TaintLabel.EXTERNAL_NETWORK, TaintLabel.UNTRUSTED_INGRESS}),
    "file_write_tool": frozenset({TaintLabel.EXTERNAL_NETWORK, TaintLabel.UNTRUSTED_INGRESS}),
    "file_edit_tool": frozenset({TaintLabel.EXTERNAL_NETWORK, TaintLabel.UNTRUSTED_INGRESS}),
    "web_fetch_tool": frozenset({TaintLabel.SECRET}),
    "browser_navigate_tool": frozenset({TaintLabel.SECRET}),
    "browser_snapshot_tool": frozenset({TaintLabel.SECRET}),
    "browser_extract_tool": frozenset({TaintLabel.SECRET}),
}

_BASH_EGRESS_RE = re.compile(
    r"(?:\bcurl\b|\bwget\b|\bnc\b|\bncat\b|\bsocat\b|\bssh\b|\bscp\b|\brsync\b|\bftp\b)[\s\S]{1,60}https?://|"
    r"(?:\bcurl\b|\bwget\b|\bnc\b|\bncat\b|\bsocat\b)\s+-[A-Za-z0-9]*[dF]",
    re.IGNORECASE,
)


class TaintTracker:
    """Accumulates taint labels and their sources for the current Agent session.

    Once a label is added, it persists for the entire session.
    This is conservative by design — we cannot know whether the LLM
    has "forgotten" the tainted data from its context.
    """

    __slots__ = ("_taints",)

    def __init__(self) -> None:
        # Maps TaintLabel to a set of sources (e.g., URLs, file paths)
        self._taints: dict[TaintLabel, set[str]] = {}

    def record(self, label: TaintLabel, source: str | None = None) -> None:
        """Record that tainted data of the given type is now in the LLM context.

        Args:
            label: The category of taint.
            source: Optional specific source of the taint (e.g., a URL).
        """
        if label not in self._taints:
            self._taints[label] = set()
            logger.warning("[TAINT] Recorded new label: %s", label)

        if source and source not in self._taints[label]:
            self._taints[label].add(source)
            logger.info("[TAINT] Added source '%s' to label %s", source, label)

    def record_ingress_taint(
        self,
        label: TaintLabel = TaintLabel.UNTRUSTED_INGRESS,
        source: str | None = None,
    ) -> None:
        """Record taint from an external inbound message (e.g. an untrusted channel webhook).

        ``reset_all_guards`` rebuilds the tracker when an agent run starts, so a label recorded before
        ``process_stream`` is gone before the first tool call; a host marks such a run with
        ``set_untrusted_ingress`` instead.
        """
        self.record(label, source)

    def record_tool_output(self, tool_name: str, tool_input: dict[str, object] | None = None) -> None:
        """Record taint from a tool's output, extracting source via safety metadata."""
        from myrm_agent_harness.agent.security.tool_registry import resolve_safety_metadata

        meta = resolve_safety_metadata(tool_name)
        if not meta.taint_label:
            return

        try:
            label = TaintLabel(meta.taint_label)
        except ValueError:
            logger.warning("[TAINT] Invalid taint label '%s' for tool %s", meta.taint_label, tool_name)
            return

        source = None
        extractor_failed = False
        if tool_input and meta.taint_extractor:
            if callable(meta.taint_extractor):
                try:
                    source = meta.taint_extractor(tool_input)
                except Exception as e:
                    logger.warning("[TAINT] Extractor failed for %s: %s", tool_name, e)
                    extractor_failed = True
            elif isinstance(meta.taint_extractor, str):
                val = tool_input.get(meta.taint_extractor)
                if val:
                    source = str(val)

        # For conditional taint tools (e.g. file_read_tool only taints on secret files):
        if label == TaintLabel.SECRET and meta.taint_extractor and source is None and not extractor_failed:
            return

        self.record(label, source if source else None)

    def check_sink(
        self,
        tool_name: str,
        tool_input: dict[str, object] | None = None,
        trusted_hosts: Collection[str] | None = None,
    ) -> dict[TaintLabel, set[str]] | None:
        """Check if calling this tool violates any taint policy.

        Returns a dictionary mapping conflicting TaintLabels to their sources, or None if clean or the call is a
        fetch or a navigation whose ``url`` / ``urls`` values are all on the trusted list. A call of any other tool is
        never exempt, whatever arguments it carries.
        """
        permission = resolve_permission_type(tool_name, tool_input)

        # One untrusted URL among several keeps the call a sink: the data could leave through it.
        if trusted_hosts and tool_input and permission in URL_BEARING_PERMISSIONS:
            hosts = url_arg_hosts(tool_input)
            if hosts and all(host_matches(host, trusted_hosts) for host in hosts):
                return None

        blocked = set(TAINT_SINK_POLICIES.get(tool_name, frozenset()))

        # Dynamic sink escalation: with SECRET taint in the session, command text shaped like a network transfer is an
        # egress, whether the bash tool runs it or a running process receives it on stdin.
        if (
            TaintLabel.SECRET in self._taints
            and tool_input
            and _BASH_EGRESS_RE.search(command_text(permission, tool_input))
        ):
            blocked.add(TaintLabel.SECRET)

        if not blocked:
            return None

        conflict_labels = set(self._taints.keys()) & blocked
        if not conflict_labels:
            return None

        return {label: self._taints[label] for label in conflict_labels}

    @property
    def labels(self) -> frozenset[TaintLabel]:
        return frozenset(self._taints.keys())

    @property
    def is_tainted(self) -> bool:
        return bool(self._taints)


_taint_tracker_var: ContextVar[TaintTracker] = ContextVar("taint_tracker")


def get_taint_tracker() -> TaintTracker:
    """Get the TaintTracker for the current async context.

    Creates a new one if none exists (lazy initialization).
    """
    try:
        return _taint_tracker_var.get()
    except LookupError:
        tracker = TaintTracker()
        _taint_tracker_var.set(tracker)
        return tracker


def reset_taint_tracker() -> None:
    """Reset taint state. Call at the start of each Agent run."""
    _taint_tracker_var.set(TaintTracker())
