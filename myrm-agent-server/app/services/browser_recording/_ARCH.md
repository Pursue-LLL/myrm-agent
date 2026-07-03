# services/browser_recording/

## 架构概述

浏览器录制会话业务层：内存态 session 生命周期、Harness capture 序列化、可选技能草稿生成。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 服务导出 | ✅ |
| `session_manager.py` | 核心 | 录制 session 注册/步进/结束 | ✅ |
| `skill_generator.py` | 扩展 | 将 capture 序列化为可安装 skill 草稿 | ✅ |
