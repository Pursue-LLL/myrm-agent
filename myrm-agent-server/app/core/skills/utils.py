"""Skill 工具函数

提供技能相关的公共工具函数，避免代码重复。
"""


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


__all__ = ["normalize_skill_name"]
