"""Prebuilt trunk workflow templates: product-to-dev main chain.

[INPUT]
- myrm_agent_harness.agent.dynamic_workflow.template_store::WorkflowTemplateStore (POS: template persistence)

[OUTPUT]
- TRUNK_TEMPLATES: five curated orchestration scripts with metadata
- TRUNK_CATALOG_VERSION: bump when any trunk script changes
- seed_trunk_templates: idempotent upsert of the five trunk records
- describe_trunk_catalog: UI/API-facing catalog metadata

[POS]
Server-owned business content for the Dynamic Workflow engine. Scripts reuse
the engine's spawn/notify/ask primitives; nothing here changes harness code.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from myrm_agent_harness.agent.dynamic_workflow.template_store import (
    WorkflowTemplateRecord,
    WorkflowTemplateStore,
)

logger = logging.getLogger(__name__)

TRUNK_CATALOG_VERSION = 1


@dataclass(frozen=True, slots=True)
class TrunkTemplate:
    """One prebuilt trunk flow: id, display copy, and orchestration script."""

    template_id: str
    display_name: str
    description: str
    placeholders: tuple[str, ...]
    script_code: str


_TRIAGE_SCRIPT = '''"""Product triage flow: collect feedback, dedupe, backfill evidence, decide."""
import json

import myrm_tools


def run(task_id, description, readonly=True):
    try:
        result = myrm_tools.spawn_subagent(
            task_id=task_id,
            agent_type="generalPurpose",
            task_description=description,
            readonly=readonly,
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    return {"task_id": task_id, **result}


myrm_tools.notify("Collecting feedback", step_index=1, total_steps=4, category="collect")
collected = run(
    "collect",
    "Collect user feedback and bug reports about: {topic}. "
    "Sources to consider: {source_hint}. Keep every original message verbatim "
    "with its source; do not summarize away details.",
    True,
)

myrm_tools.notify("Deduping issues", step_index=2, total_steps=4, category="define")
defined = run(
    "define",
    "Deduplicate the collected items into distinct problems. For each problem "
    "give a one-sentence definition. Collected items: "
    + str(collected.get("result", "")),
    True,
)

myrm_tools.notify("Backfilling evidence", step_index=3, total_steps=4, category="evidence")
evidenced = run(
    "evidence",
    "For each defined problem, attach current code status and user evidence "
    "found in the workspace. Mark problems without evidence as NEEDS-EVIDENCE. "
    "Problems: " + str(defined.get("result", "")),
    True,
)

myrm_tools.notify("Writing decision", step_index=4, total_steps=4, category="decide")
decision = run(
    "decide",
    "Write an evidence-backed decision: which problems to fix, in which order, "
    "and why. Drop NEEDS-EVIDENCE items with a follow-up question. Evidence: "
    + str(evidenced.get("result", "")),
    True,
)

print(json.dumps({"collected": collected, "defined": defined, "evidenced": evidenced, "decision": decision}, indent=2, ensure_ascii=False))
'''

_DELIVERY_SCRIPT = '''"""Product delivery flow: draft PRD, fact-check, completeness review."""
import json

import myrm_tools


def run(task_id, description, readonly=True):
    try:
        result = myrm_tools.spawn_subagent(
            task_id=task_id,
            agent_type="generalPurpose",
            task_description=description,
            readonly=readonly,
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    return {"task_id": task_id, **result}


myrm_tools.notify("Drafting proposal", step_index=1, total_steps=3, category="draft")
draft = run(
    "draft",
    "Draft a PRD/technical proposal about: {topic}. Audience: {audience}. "
    "Structure: background, goals, non-goals, proposal, risks, rollout.",
    True,
)

myrm_tools.notify("Fact checking", step_index=2, total_steps=3, category="verify")
checked = run(
    "check",
    "Independently fact-check every technical claim in this draft against the "
    "workspace code. List each claim as VERIFIED, WRONG (with correction), or "
    "UNVERIFIABLE (with what is missing). Draft: " + str(draft.get("result", "")),
    True,
)

myrm_tools.notify("Completeness review", step_index=3, total_steps=3, category="review")
reviewed = run(
    "review",
    "Review the checked draft for completeness: missing edge cases, missing "
    "rollback plan, missing acceptance criteria. Output the final proposal plus "
    "an open-questions list. Checked draft: " + str(checked.get("result", "")),
    True,
)

print(json.dumps({"draft": draft, "checked": checked, "reviewed": reviewed}, indent=2, ensure_ascii=False))
'''

_IMPLEMENT_SCRIPT = '''"""Dev implementation flow: plan, bounded coding, automated tests, human merge."""
import json

import myrm_tools


def run(task_id, description, readonly):
    try:
        result = myrm_tools.spawn_subagent(
            task_id=task_id,
            agent_type="generalPurpose",
            task_description=description,
            readonly=readonly,
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    return {"task_id": task_id, **result}


myrm_tools.notify("Writing tech plan", step_index=1, total_steps=4, category="plan")
plan = run(
    "plan",
    "Write a minimal technical plan for this task: {task}. Hard boundary, do "
    "not cross it: {scope_boundary}. List files to touch and tests to run.",
    True,
)

myrm_tools.notify("Implementing", step_index=2, total_steps=4, category="code")
coded = run(
    "code",
    "Implement strictly inside this boundary: {scope_boundary}. Task: {task}. "
    "Follow the plan: " + str(plan.get("result", "")) + " Do not refactor "
    "anything outside the boundary. Do not commit.",
    False,
)

myrm_tools.notify("Running tests", step_index=3, total_steps=4, category="test")
tested = run(
    "test",
    "Run the automated tests for the changed code. Test command hint: "
    "{test_command}. Report pass/fail per test with output excerpts. Code "
    "changes: " + str(coded.get("result", "")),
    False,
)

myrm_tools.notify("Handoff to human", step_index=4, total_steps=4, category="handoff")
print(json.dumps({"plan": plan, "coded": coded, "tested": tested, "merge": "human-takeover"}, indent=2, ensure_ascii=False))
'''

_BUGFIX_SCRIPT = '''"""Bugfix flow: reproduce, root-cause, minimal fix, regression check."""
import json

import myrm_tools


def run(task_id, description, readonly):
    try:
        result = myrm_tools.spawn_subagent(
            task_id=task_id,
            agent_type="generalPurpose",
            task_description=description,
            readonly=readonly,
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    return {"task_id": task_id, **result}


myrm_tools.notify("Reproducing", step_index=1, total_steps=4, category="repro")
repro = run(
    "repro",
    "Reproduce this failure: {error_report}. Stack trace: {stack_trace}. "
    "Report exact reproduction steps or state why it cannot be reproduced.",
    True,
)

myrm_tools.notify("Locating root cause", step_index=2, total_steps=4, category="cause")
cause = run(
    "cause",
    "Find the root cause of the reproduced failure. Distinguish root cause "
    "from symptoms. Reproduction: " + str(repro.get("result", "")),
    True,
)

myrm_tools.notify("Applying minimal fix", step_index=3, total_steps=4, category="fix")
fixed = run(
    "fix",
    "Apply the smallest fix that resolves the root cause, nothing more. Root "
    "cause: " + str(cause.get("result", "")) + " Do not commit.",
    False,
)

myrm_tools.notify("Regression check", step_index=4, total_steps=4, category="regress")
regressed = run(
    "regress",
    "Run the relevant automated tests to confirm the fix and catch "
    "regressions. Fix: " + str(fixed.get("result", "")),
    False,
)

print(json.dumps({"repro": repro, "cause": cause, "fixed": fixed, "regressed": regressed}, indent=2, ensure_ascii=False))
'''

_CONSOLIDATE_SCRIPT = '''"""Product consolidation flow: diff the merge, sync wiki docs."""
import json

import myrm_tools


def run(task_id, description, readonly):
    try:
        result = myrm_tools.spawn_subagent(
            task_id=task_id,
            agent_type="generalPurpose",
            task_description=description,
            readonly=readonly,
        )
    except Exception as exc:
        result = {"success": False, "error": str(exc)}
    return {"task_id": task_id, **result}


myrm_tools.notify("Reading merged changes", step_index=1, total_steps=3, category="diff")
diffed = run(
    "diff",
    "Read what merge {merge_ref} actually changed in behavior (not style). "
    "Focus area: {area}. List user-visible behavior changes only.",
    True,
)

myrm_tools.notify("Comparing docs", step_index=2, total_steps=3, category="compare")
compared = run(
    "compare",
    "Compare the behavior changes against the current wiki/feature docs. For "
    "each change mark docs as CURRENT, STALE (with the outdated text), or "
    "MISSING. Changes: " + str(diffed.get("result", "")),
    True,
)

myrm_tools.notify("Syncing docs", step_index=3, total_steps=3, category="sync")
synced = run(
    "sync",
    "Update the STALE and MISSING docs to match the merged implementation. "
    "Keep edits minimal and factual. Comparison: " + str(compared.get("result", "")),
    False,
)

print(json.dumps({"diffed": diffed, "compared": compared, "synced": synced}, indent=2, ensure_ascii=False))
'''

TRUNK_TEMPLATES: tuple[TrunkTemplate, ...] = (
    TrunkTemplate(
        template_id="trunk-product-triage",
        display_name="Trunk · Product triage",
        description="Collect feedback, dedupe into problems, backfill evidence, write a decision.",
        placeholders=("topic", "source_hint"),
        script_code=_TRIAGE_SCRIPT,
    ),
    TrunkTemplate(
        template_id="trunk-product-delivery",
        display_name="Trunk · Product delivery",
        description="Draft a proposal, fact-check it against code, review completeness.",
        placeholders=("topic", "audience"),
        script_code=_DELIVERY_SCRIPT,
    ),
    TrunkTemplate(
        template_id="trunk-dev-implement",
        display_name="Trunk · Dev implement",
        description="Plan, code inside a hard boundary, test, hand merge to a human.",
        placeholders=("task", "scope_boundary", "test_command"),
        script_code=_IMPLEMENT_SCRIPT,
    ),
    TrunkTemplate(
        template_id="trunk-bugfix",
        display_name="Trunk · Bugfix",
        description="Reproduce, root-cause, minimal fix, regression check.",
        placeholders=("error_report", "stack_trace"),
        script_code=_BUGFIX_SCRIPT,
    ),
    TrunkTemplate(
        template_id="trunk-product-consolidate",
        display_name="Trunk · Product consolidate",
        description="Diff a merge, compare docs, sync stale wiki content.",
        placeholders=("merge_ref", "area"),
        script_code=_CONSOLIDATE_SCRIPT,
    ),
)

TRUNK_TEMPLATE_IDS: frozenset[str] = frozenset(t.template_id for t in TRUNK_TEMPLATES)


def is_trunk_template(template_id: str) -> bool:
    """Return True when the id belongs to the prebuilt trunk catalog."""
    return template_id in TRUNK_TEMPLATE_IDS


def describe_trunk_catalog() -> list[dict[str, object]]:
    """Return UI/API-facing catalog metadata (no script bodies)."""
    return [
        {
            "template_id": template.template_id,
            "display_name": template.display_name,
            "description": template.description,
            "placeholders": list(template.placeholders),
            "catalog_version": TRUNK_CATALOG_VERSION,
        }
        for template in TRUNK_TEMPLATES
    ]


def seed_trunk_templates(store: WorkflowTemplateStore) -> list[WorkflowTemplateRecord]:
    """Idempotently upsert the five trunk templates (trust_latch off)."""
    records: list[WorkflowTemplateRecord] = []
    for template in TRUNK_TEMPLATES:
        record = store.save_template(
            template_id=template.template_id,
            display_name=template.display_name,
            script_code=template.script_code,
            trust_latch=False,
        )
        records.append(record)
    logger.info("[Trunk] Seeded %d templates (catalog v%d)", len(records), TRUNK_CATALOG_VERSION)
    return records
