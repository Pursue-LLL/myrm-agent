#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""清理 Qdrant 嵌入式模式的残留锁文件

用法:
    python scripts/cleanup_qdrant_locks.py
    python scripts/cleanup_qdrant_locks.py --path ./data/memory
"""

import argparse
import os
import time
from pathlib import Path


def _get_default_qdrant_path() -> str:
    """Get default Qdrant data path from environment variable or fallback."""
    data_dir = os.environ.get("MYRM_DATA_DIR", str(Path.home() / ".myrm"))
    return str(Path(data_dir) / "qdrant")


def cleanup_qdrant_locks(base_path: str | None = None, max_age_seconds: int = 30) -> int:
    """清理 Qdrant 嵌入式模式的残留锁文件

    Args:
        base_path: Qdrant 数据存储的基础路径，默认从 MYRM_DATA_DIR 环境变量读取
        max_age_seconds: 锁文件的最大年龄（秒），超过此时间的锁文件将被删除

    Returns:
        清理的锁文件数量
    """
    if base_path is None:
        base_path = _get_default_qdrant_path()
    base = Path(base_path)
    if not base.exists():
        print(f"⚠️  路径不存在: {base_path}")
        return 0

    cleaned_count = 0
    current_time = time.time()

    # 查找所有 .lock 文件
    for lock_file in base.rglob(".lock"):
        try:
            lock_stat = lock_file.stat()
            lock_age = current_time - lock_stat.st_mtime

            if lock_age > max_age_seconds:
                print(f"🧹 删除过期锁文件: {lock_file} (年龄: {int(lock_age)}秒)")
                lock_file.unlink()
                cleaned_count += 1
            else:
                print(f"⏳ 保留锁文件: {lock_file} (年龄: {int(lock_age)}秒，小于 {max_age_seconds}秒)")
        except PermissionError:
            print(f"❌ 无法删除锁文件（可能正在使用）: {lock_file}")
        except Exception as e:
            print(f"⚠️  处理锁文件时出错 {lock_file}: {e}")

    return cleaned_count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="清理 Qdrant 嵌入式模式的残留锁文件")
    parser.add_argument(
        "--path",
        type=str,
        default=None,
        help=f"Qdrant 数据存储的基础路径（默认: {_get_default_qdrant_path()}）",
    )
    parser.add_argument(
        "--max-age",
        type=int,
        default=30,
        help="锁文件的最大年龄（秒），超过此时间的锁文件将被删除（默认: 30）",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制删除所有锁文件（忽略年龄）",
    )

    args = parser.parse_args()

    max_age = 0 if args.force else args.max_age

    print(f"🔍 扫描锁文件: {args.path}")
    print(f"📅 最大年龄: {max_age}秒" if max_age > 0 else "⚡ 强制模式: 删除所有锁文件")
    print()

    cleaned = cleanup_qdrant_locks(args.path, max_age)

    print()
    if cleaned > 0:
        print(f"✅ 已清理 {cleaned} 个锁文件")
    else:
        print("✅ 没有需要清理的锁文件")
