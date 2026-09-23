"""Wiki writeback domain service managing usage ledgers and review slips.

[INPUT]
- app.services.wiki.vault::resolve_wiki_vault_path
- myrm_agent_harness.toolkits.wiki.core.negative_exclusion_policy::evaluate_exclusion_policy
- myrm_agent_harness.toolkits.wiki.core.structure::WikiStructure
- myrm_agent_harness.toolkits.wiki.core.frontmatter_contract::WikiPageType, WikiPublishStatus
- app.services.wiki.writeback.schemas

[OUTPUT]
- WikiWritebackService, get_writeback_service

[POS]
Orchestrates task delivery usage tracking, negative rule filtering,
and author review slip confirmation to safe selective writeback.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from pathlib import Path

from myrm_agent_harness.toolkits.wiki.core.negative_exclusion_policy import (
    evaluate_exclusion_policy,
)
from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure

from app.services.wiki.vault import resolve_wiki_vault_path
from app.services.wiki.writeback.schemas import (
    ReviewSlipBatch,
    ReviewSlipOption,
    ReviewSlipQuestion,
    UsageLedgerRecord,
    WritebackApplyRequest,
    WritebackApplyResult,
)

logger = logging.getLogger(__name__)


class WikiWritebackService:
    """Service handling usage ledger persistence, review slip synthesis, and writeback commit."""

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = workspace_root

    def _get_structure(self, agent_id: str) -> WikiStructure:
        vault_path = resolve_wiki_vault_path(agent_id)
        structure = WikiStructure(base_dir=vault_path)
        structure.ensure_structure()
        return structure

    def record_usage_ledger(
        self,
        agent_id: str,
        record: UsageLedgerRecord,
    ) -> Path:
        """Persist a task usage ledger into deliverables/ledgers/."""
        structure = self._get_structure(agent_id)
        ledgers_dir = structure.deliverables_dir / "ledgers"
        ledgers_dir.mkdir(parents=True, exist_ok=True)

        safe_task_id = re.sub(r"[^\w\s-]", "", record.task_id).strip() or "task_unknown"
        target_path = ledgers_dir / f"{safe_task_id}.json"

        target_path.write_text(
            record.model_dump_json(indent=2),
            encoding="utf-8",
        )
        logger.info(
            "Persisted usage ledger for task %s to %s",
            record.task_id,
            target_path,
        )
        return target_path

    def generate_review_slip(
        self,
        agent_id: str,
        task_id: str,
        task_title: str,
        candidate_insights: list[dict[str, str]],
    ) -> ReviewSlipBatch:
        """
        Synthesize up to 3-5 structured decision questions from candidate insights,
        enforcing negative exclusion rules to filter ephemeral/unsafe items.
        """
        questions: list[ReviewSlipQuestion] = []
        excluded_count = 0

        for idx, insight in enumerate(candidate_insights):
            if len(questions) >= 5:
                break

            topic = insight.get("topic", "").strip() or f"Candidate Insight {idx + 1}"
            content = insight.get("content", "").strip()
            rationale = insight.get("rationale", "").strip() or "在任务交付中验证的高价值经验"

            if not content:
                continue

            # Hard boundary guard: evaluate 5 negative exclusion categories
            matches = evaluate_exclusion_policy(content, title=topic)
            if matches:
                excluded_count += 1
                logger.info(
                    "Excluding candidate '%s' from writeback: %s (%s)",
                    topic,
                    matches[0].category,
                    matches[0].rationale,
                )
                continue

            q_id = f"q_{idx + 1}_{re.sub(r'[^a-zA-Z0-9]', '_', topic)[:16]}"
            default_layer = insight.get("recommended_layer", "methods")
            is_method = default_layer == "methods"

            options = [
                ReviewSlipOption(
                    id="opt_method",
                    label="沉淀为通用方法论 (知识库)",
                    recommended=is_method,
                    target_layer="methods",
                ),
                ReviewSlipOption(
                    id="opt_claim",
                    label="归档为主张与观点 (待验证)",
                    recommended=not is_method,
                    target_layer="claims",
                ),
                ReviewSlipOption(
                    id="opt_deliverable_only",
                    label="仅保留在当前任务交付物",
                    recommended=False,
                    target_layer="deliverables_only",
                ),
            ]

            questions.append(
                ReviewSlipQuestion(
                    question_id=q_id,
                    topic=topic,
                    candidate_content=content,
                    rationale=rationale,
                    options=options,
                    selected_option_id=options[0].id if is_method else options[1].id,
                )
            )

        now_iso = datetime.now(UTC).isoformat(timespec="seconds")
        return ReviewSlipBatch(
            task_id=task_id,
            title=task_title,
            generated_at=now_iso,
            questions=questions,
            excluded_matches_count=excluded_count,
        )

    def apply_writeback(
        self,
        agent_id: str,
        request: WritebackApplyRequest,
    ) -> WritebackApplyResult:
        """Commit user approved review decisions into the designated layer."""
        structure = self._get_structure(agent_id)
        committed_count = 0
        discarded_count = 0
        created_paths: list[str] = []

        for item in request.decisions:
            if item.target_layer in ("deliverables_only", "discard"):
                discarded_count += 1
                continue

            # Safe filename slug
            slug = re.sub(r"[^\w\s-]", "", item.candidate_title.lower()).strip()
            slug = re.sub(r"[\s_]+", "-", slug).strip("-") or "untitled-insight"

            if item.target_layer == "methods":
                target_file = structure.methods_dir / f"{slug}.md"
                page_type = "method"
            else:
                target_file = structure.claims_dir / f"{slug}.md"
                page_type = "claim"

            # Render YAML frontmatter adhering to Draft-to-Live gate
            now_iso = datetime.now(UTC).isoformat(timespec="seconds")
            file_content = (
                f"---\n"
                f"title: \"{item.candidate_title}\"\n"
                f"type: {page_type}\n"
                f"publish_status: draft\n"
                f"source_task_id: \"{request.task_id}\"\n"
                f"created_at: \"{now_iso}\"\n"
                f"---\n\n"
                f"{item.candidate_content}\n"
            )

            target_file.parent.mkdir(parents=True, exist_ok=True)
            target_file.write_text(file_content, encoding="utf-8")

            rel_path = str(target_file.relative_to(structure.base_dir))
            created_paths.append(rel_path)
            committed_count += 1
            logger.info("Committed writeback insight to %s", rel_path)

        return WritebackApplyResult(
            task_id=request.task_id,
            committed_count=committed_count,
            discarded_count=discarded_count,
            created_paths=created_paths,
            message=f"Successfully committed {committed_count} items (discarded {discarded_count})",
        )


_service_instance: WikiWritebackService | None = None


def get_writeback_service(workspace_root: Path | None = None) -> WikiWritebackService:
    """Get singleton instance of WikiWritebackService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = WikiWritebackService(workspace_root=workspace_root)
    return _service_instance
