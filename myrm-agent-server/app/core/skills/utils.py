"""Skill 工具函数

提供技能相关的公共工具函数，避免代码重复。
"""

import json


def normalize_skill_name(name: str) -> str:
    """标准化技能名称，统一以 _skill 结尾用于 LLM 识别

    规则：
    - 如果已经以 _skill 结尾，保持不变
    - 否则，替换 - 为 _，并添加 _skill 后缀

    Args:
        name: 原始技能名称

    Returns:
        标准化后的技能名称

    Raises:
        ValueError: 如果名称为空或只包含空白字符

    Examples:
        >>> normalize_skill_name("my-skill")
        'my_skill_skill'
        >>> normalize_skill_name("my_skill")
        'my_skill'
        >>> normalize_skill_name("data_analysis")
        'data_analysis_skill'
    """
    if not name or not name.strip():
        raise ValueError("Skill name cannot be empty or whitespace")

    # 去除首尾空白
    name = name.strip()

    # 如果已经以 _skill 结尾，保持不变
    if name.endswith("_skill"):
        return name

    # 替换 - 为 _
    normalized = name.replace("-", "_")

    # 添加 _skill 后缀（如果没有）
    return normalized if normalized.endswith("_skill") else f"{normalized}_skill"


def yaml_scalar(value: str) -> str:
    """Render ``value`` as a YAML double-quoted scalar for SKILL.md frontmatter.

    JSON string syntax is a subset of YAML double-quoted scalars, so colons, ``#``, quotes, backslashes
    and line breaks in model-generated text stay data instead of breaking or retyping the frontmatter.
    """
    return json.dumps(value, ensure_ascii=False)


def resolve_skill_description(description: str | None, trigger_condition: str | None, name: str) -> str:
    """Pick the text skill discovery matches on: the description, else when to use it, else the name."""
    for candidate in (description, trigger_condition):
        text = (candidate or "").strip()
        if text:
            return text
    return name


__all__ = ["normalize_skill_name", "resolve_skill_description", "yaml_scalar"]
