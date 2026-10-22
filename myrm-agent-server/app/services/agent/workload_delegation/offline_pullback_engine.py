"""离线异步完成推送与成果自愈回拉引擎 (Offline Pullback Engine)。

汲取字节跳动“豆包工作”桌面端核心架构设计：
1. 云端沙箱长任务执行完成后，自动向移动端/桌面端推送完成通知；
2. 本地电脑重新开机联网时，一键或自适应将云端成果增量 Patch 回拉同步至本地工作区；
3. 基于三方合并原则检查基线冲突，杜绝暴力覆盖，实现平滑自愈闭环。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping

logger = logging.getLogger(__name__)


class MergeStatus(StrEnum):
    """回拉合并状态枚举。"""

    CLEAN_MERGE = "clean_merge"
    CONFLICT_DETECTED = "conflict_detected"
    ALREADY_UP_TO_DATE = "already_up_to_date"


@dataclass(frozen=True, slots=True)
class PullbackBundle:
    """云端执行完成生成的成果与增量回拉包。"""

    task_id: str
    session_id: str
    cloud_files: Mapping[str, str]
    base_file_hashes: Mapping[str, str]
    artifacts_created: tuple[str, ...]
    execution_summary: str
    completed_at: float = field(default_factory=time.time)


@dataclass(frozen=True, slots=True)
class PullbackApplyResult:
    """回拉应用到本地工作区的结果报告。"""

    task_id: str
    status: MergeStatus
    applied_files: tuple[str, ...]
    conflicted_files: tuple[str, ...]
    summary: str


class OfflinePullbackEngine:
    """成果自愈回拉引擎：负责将云端沙箱生成的最新工件与代码 Diff 合并回本地。"""

    @staticmethod
    def inspect_and_merge(
        bundle: PullbackBundle,
        local_files: Mapping[str, str],
    ) -> tuple[dict[str, str], PullbackApplyResult]:
        """将云端成果包与本地工作区进行冲突检测与原子合并。

        规则：
        1. 本地未修改（与 base_hash 一致），直接更新为云端新内容；
        2. 本地新创建的文件不受影响；
        3. 本地在委派期间被意外修改（与 base_hash 不一致且与云端新内容不一致），判定为冲突。
        """
        merged_files: dict[str, str] = dict(local_files)
        applied: list[str] = []
        conflicts: list[str] = []

        for path, cloud_content in bundle.cloud_files.items():
            current_local = local_files.get(path)

            # 新增文件或本地文件与云端完全一致
            if current_local is None:
                merged_files[path] = cloud_content
                applied.append(path)
            elif current_local == cloud_content:
                # 已经相同，幂等忽略
                continue
            else:
                # 本地存在且内容不同：检查基线哈希
                base_hash = bundle.base_file_hashes.get(path)
                import hashlib
                current_local_hash = hashlib.sha256(current_local.encode("utf-8")).hexdigest()

                if base_hash is None or current_local_hash == base_hash:
                    # 本地自委派以来未改动，安全应用云端变更
                    merged_files[path] = cloud_content
                    applied.append(path)
                else:
                    # 本地被修改过且不同于云端，标记冲突并插入冲突标记
                    conflicts.append(path)
                    conflict_content = (
                        f"<<<<<<< LOCAL (Desktop)\n"
                        f"{current_local}\n"
                        f"=======\n"
                        f"{cloud_content}\n"
                        f">>>>>>> CLOUD (Sandbox)\n"
                    )
                    merged_files[path] = conflict_content

        if conflicts:
            status = MergeStatus.CONFLICT_DETECTED
            summary = f"Pullback completed with {len(conflicts)} conflict(s) requiring user resolution."
        elif applied:
            status = MergeStatus.CLEAN_MERGE
            summary = f"Successfully pulled back and merged {len(applied)} file(s) into local workspace."
        else:
            status = MergeStatus.ALREADY_UP_TO_DATE
            summary = "Local workspace is already up to date with cloud output."

        result = PullbackApplyResult(
            task_id=bundle.task_id,
            status=status,
            applied_files=tuple(sorted(applied)),
            conflicted_files=tuple(sorted(conflicts)),
            summary=summary,
        )
        return merged_files, result
