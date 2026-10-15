"""Skill 工具函数

[INPUT]
- json: 标准库 JSON 序列化（YAML 双引号标量的转义依据）

[OUTPUT]
- normalize_skill_name: 技能名称标准化（统一 _skill 后缀）
- resolve_skill_description: 技能描述回退（description → trigger_condition → name）
- yaml_scalar: 把模型生成文本渲染为 YAML 双引号标量，供 SKILL.md frontmatter 使用

[POS]
技能公共工具函数。名称标准化、描述回退与 frontmatter 标量转义的单一实现，避免各落盘路径重复。
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
    A raw NEL (U+0085) is the one character JSON leaves unescaped that YAML folds into a space, so it is escaped.
    """
    return json.dumps(value, ensure_ascii=False).replace("\x85", "\\x85")


def resolve_skill_description(description: str | None, trigger_condition: str | None, name: str) -> str:
    """Pick the text skill discovery matches on: the description, else when to use it, else the name."""
    for candidate in (description, trigger_condition):
        text = (candidate or "").strip()
        if text:
            return text
    return name


__all__ = ["normalize_skill_name", "resolve_skill_description", "yaml_scalar"]
