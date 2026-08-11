"""包装模块结果类型（打包/解包结果数据类）。

[INPUT]
- myrm_agent_harness.agent.skills.security.content_sanitizer::Redaction (POS: 脱敏条目)

[OUTPUT]
- PackageResult: 技能打包结果（zip 内容、脱敏预览、回归门禁计数）
- UnpackResult: 技能解包注册结果（skill_id、还原 eval_cases 数）

[POS]
skills/packaging 门面的结果数据类；无业务逻辑，仅承载数据。
"""

from dataclasses import dataclass

from myrm_agent_harness.agent.skills.security.content_sanitizer import Redaction


@dataclass
class PackageResult:
    """打包结果"""

    success: bool
    zip_content: bytes | None
    filename: str | None
    error: str | None = None
    redactions: dict[str, list[Redaction]] | None = (
        None  # filename -> list of redactions
    )
    is_safe: bool = (
        True  # True if no redactions were needed or if they were applied and user confirmed
    )
    eval_cases_count: int = 0  # 包内 evals.json 回归门禁用例数


@dataclass
class UnpackResult:
    """解包结果 (Server 业务层包装)"""

    success: bool
    skill_id: str | None = None
    skill_name: str | None = None
    error: str | None = None
    restored_eval_cases: int = 0  # 从包内 evals.json 还原的回归门禁用例数
