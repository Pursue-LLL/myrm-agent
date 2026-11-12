"""[INPUT]
- myrm_agent_harness.backends.skills._content_memo::ContentMemo (POS: Listing skills re-derives the same facts (frontmatter, security scan, token count) from unchanged SKILL.md text on every agent turn.)
- myrm_agent_harness.backends.skills._utils.frontmatter::SkillFrontmatter / SkillMetadataError (POS: skills _utils 子包的一部分；由 __init__.py 聚合导出。)
- myrm_agent_harness.backends.skills.types::SkillContract / SkillContractJudgment / SkillContractTrap / SkillContractVerification / SkillRequires (POS: Framework generic skill system. The stable public entry point stays at ``backends.skills.types``; the nine ``types_*`` implementation modules are co-located here under this facade.)

[OUTPUT]
- _parse_requires: Parse dependency requirements from frontmatter.
- _extract_str_list: Extract a list of strings from a YAML value, tolerating various formats.
- _require_contract_mapping: _require_contract_mapping
- _parse_contract_steps: _parse_contract_steps
- _parse_contract_dependencies: _parse_contract_dependencies
- _parse_contract_success_criteria: _parse_contract_success_criteria
- _parse_contract_duration: _parse_contract_duration
- _parse_contract_judgments: _parse_contract_judgments
- _parse_contract_traps: _parse_contract_traps
- _parse_contract_verifications: _parse_contract_verifications
- _parse_skill_contract: _parse_skill_contract

[POS]
skills _utils 子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import math

from myrm_agent_harness.backends.skills._content_memo import ContentMemo
from myrm_agent_harness.backends.skills._utils.frontmatter import SkillFrontmatter, SkillMetadataError
from myrm_agent_harness.backends.skills.types import (
    SkillContract,
    SkillContractJudgment,
    SkillContractTrap,
    SkillContractVerification,
    SkillRequires,
)

logger = logging.getLogger(__name__)

def _parse_requires(parsed: dict[str, object]) -> SkillRequires | None:
    """Parse dependency requirements from frontmatter.

    Args:
        parsed: Parsed YAML frontmatter dict

    Returns:
        SkillRequires if requirements are declared, None otherwise
    """
    raw_requires = parsed.get("requires")
    if not isinstance(raw_requires, dict):
        return None

    bins = _extract_str_list(raw_requires.get("bins"))
    env = _extract_str_list(raw_requires.get("env"))
    config = _extract_str_list(raw_requires.get("config"))

    if not bins and not env and not config:
        return None

    return SkillRequires(bins=bins, env=env, config=config)


def _extract_str_list(value: object) -> list[str]:
    """Extract a list of strings from a YAML value, tolerating various formats."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if item is not None and str(item).strip()]
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    return []


def _require_contract_mapping(raw_contract: object, skill_dir_name: str) -> dict[str, object]:
    if not isinstance(raw_contract, dict):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract must be a YAML mapping with structured fields")
    return raw_contract


def _parse_contract_steps(raw_contract: dict[str, object], skill_dir_name: str) -> tuple[str, ...]:
    return tuple(_extract_str_list(raw_contract.get("steps")))


def _parse_contract_dependencies(raw_contract: dict[str, object]) -> tuple[str, ...]:
    return tuple(_extract_str_list(raw_contract.get("dependencies")))


def _parse_contract_success_criteria(raw_contract: dict[str, object], skill_dir_name: str) -> str:
    raw_value = raw_contract.get("success_criteria")
    if raw_value is None:
        return ""
    if not isinstance(raw_value, str):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.success_criteria must be a string")
    return raw_value.strip()


def _parse_contract_duration(raw_contract: dict[str, object], skill_dir_name: str) -> float | None:
    raw_value = raw_contract.get("estimated_duration_seconds")
    if raw_value is None:
        return None
    message = f"Skill '{skill_dir_name}' contract.estimated_duration_seconds must be numeric"
    if not isinstance(raw_value, int | float | str):
        raise SkillMetadataError(message)
    try:
        duration = float(raw_value)
    except ValueError as exc:
        raise SkillMetadataError(message) from exc
    if math.isnan(duration) or math.isinf(duration):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.estimated_duration_seconds must be finite")
    if duration < 0:
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.estimated_duration_seconds cannot be negative")
    return duration


def _parse_contract_judgments(
    raw_contract: dict[str, object],
    skill_dir_name: str,
) -> tuple[SkillContractJudgment, ...]:
    raw_items = raw_contract.get("key_judgments")
    if raw_items is None:
        return ()
    if not isinstance(raw_items, list):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.key_judgments must be a list")

    judgments: list[SkillContractJudgment] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.key_judgments[{index}] must be a mapping")
        judgment_id = str(item.get("judgment_id", "")).strip()
        description = str(item.get("description", "")).strip()
        condition = str(item.get("condition", "")).strip()
        true_branch = str(item.get("true_branch", "")).strip()
        false_branch = str(item.get("false_branch", "")).strip()
        if not all((judgment_id, description, condition, true_branch, false_branch)):
            raise SkillMetadataError(
                f"Skill '{skill_dir_name}' contract.key_judgments[{index}] has missing required fields"
            )
        rationale_raw = item.get("rationale")
        rationale = str(rationale_raw).strip() if rationale_raw is not None else None
        judgments.append(
            SkillContractJudgment(
                judgment_id=judgment_id,
                description=description,
                condition=condition,
                true_branch=true_branch,
                false_branch=false_branch,
                rationale=rationale or None,
            )
        )
    return tuple(judgments)


def _parse_contract_traps(
    raw_contract: dict[str, object],
    skill_dir_name: str,
) -> tuple[SkillContractTrap, ...]:
    raw_items = raw_contract.get("potential_traps")
    if raw_items is None:
        return ()
    if not isinstance(raw_items, list):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.potential_traps must be a list")

    traps: list[SkillContractTrap] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.potential_traps[{index}] must be a mapping")
        description = str(item.get("description", "")).strip()
        mitigation = str(item.get("mitigation", "")).strip()
        if not description or not mitigation:
            raise SkillMetadataError(
                f"Skill '{skill_dir_name}' contract.potential_traps[{index}] requires description and mitigation"
            )
        severity_raw = item.get("severity")
        severity = str(severity_raw).strip() if severity_raw is not None else "medium"
        trigger_raw = item.get("trigger_condition")
        trigger_condition = str(trigger_raw).strip() if trigger_raw is not None else None
        traps.append(
            SkillContractTrap(
                description=description,
                mitigation=mitigation,
                severity=severity or "medium",
                trigger_condition=trigger_condition or None,
            )
        )
    return tuple(traps)


def _parse_contract_verifications(
    raw_contract: dict[str, object],
    skill_dir_name: str,
) -> tuple[SkillContractVerification, ...]:
    raw_items = raw_contract.get("verification_steps")
    if raw_items is None:
        return ()
    if not isinstance(raw_items, list):
        raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.verification_steps must be a list")

    verifications: list[SkillContractVerification] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            raise SkillMetadataError(f"Skill '{skill_dir_name}' contract.verification_steps[{index}] must be a mapping")
        step_id = str(item.get("step_id", "")).strip()
        description = str(item.get("description", "")).strip()
        validation_method = str(item.get("validation_method", "")).strip()
        if not step_id or not description or not validation_method:
            raise SkillMetadataError(
                f"Skill '{skill_dir_name}' contract.verification_steps[{index}] has missing required fields"
            )
        expected_output_raw = item.get("expected_output")
        expected_output = str(expected_output_raw).strip() if expected_output_raw is not None else None
        verifications.append(
            SkillContractVerification(
                step_id=step_id,
                description=description,
                validation_method=validation_method,
                expected_output=expected_output or None,
                is_required=bool(item.get("is_required", True)),
            )
        )
    return tuple(verifications)


def _parse_skill_contract(parsed: dict[str, object], skill_dir_name: str) -> SkillContract | None:
    raw_contract = parsed.get("contract")
    if raw_contract is None:
        return None

    contract_map = _require_contract_mapping(raw_contract, skill_dir_name)
    return SkillContract(
        steps=_parse_contract_steps(contract_map, skill_dir_name),
        key_judgments=_parse_contract_judgments(contract_map, skill_dir_name),
        potential_traps=_parse_contract_traps(contract_map, skill_dir_name),
        verification_steps=_parse_contract_verifications(contract_map, skill_dir_name),
        dependencies=_parse_contract_dependencies(contract_map),
        estimated_duration_seconds=_parse_contract_duration(contract_map, skill_dir_name),
        success_criteria=_parse_contract_success_criteria(contract_map, skill_dir_name),
    )


_FRONTMATTER_MEMO = ContentMemo[SkillFrontmatter]("skill-frontmatter")
