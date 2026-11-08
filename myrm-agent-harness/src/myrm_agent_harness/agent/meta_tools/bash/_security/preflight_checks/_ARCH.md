# bash/_security/preflight_checks/

## 架构概述

bash 命令执行前的安全检查：每个文件一类检查，`__init__.py` 聚合并保持原有公开函数名。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出全部预检函数与共享常量 | ✅ |
| `tool_guard.py` | 核心 | 阻断 bash 中的 myrm_tools（AST/sh -c/-m/管道/引用脚本） | ✅ |
| `url_guard.py` | 核心 | URL 数据外泄拦截 | ✅ |
| `destructive.py` | 核心 | 破坏性命令拦截与高风险命令评估 | ✅ |
| `interactive.py` | 核心 | 交互式命令识别 | ✅ |
| `packages.py` | 核心 | 安装包存在性校验 | ✅ |
| `background.py` | 核心 | 未加引号的后台 `&` 检测 | ✅ |

## 依赖关系

- 各模块无横向依赖，全部通过 `__init__.py` 聚合。
