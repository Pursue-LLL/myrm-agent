# scanning/patterns/

## 架构概述

技能安全扫描的纯数据模式库：按威胁类别分组，`__init__.py` 汇总 registry，保持扫描顺序不变。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 按原顺序导出 `ALL_PATTERN_GROUPS` 与各模式组 |
| `types.py` | `PatternList` 类型别名 |
| `injection.py` | prompt / command / code injection |
| `exfiltration.py` | 凭据、数据外泄、提示词外泄 |
| `filesystem.py` | 文件系统、进程、破坏性、持久化、路径穿越 |
| `network.py` | 网络、DNS 隧道、反弹 shell、挖矿、容器逃逸 |
| `system.py` | 屏幕/输入、内存、提权、环境、反射、反序列化、日志、计划任务、供应链、混淆 |
