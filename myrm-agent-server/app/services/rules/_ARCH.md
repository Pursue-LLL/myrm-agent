# Server Default Stream Rules Architecture

## 架构概述

提供业务层默认安全与合规流式防护规则，包含高危命令拦截与凭证数据防泄露。

## 文件清单

| 文件 | 地位 | 职责 |
| --- | --- | --- |
| `__init__.py` | 入口 | 模块导出 |
| `default_rules.py` | 核心 | 预置生产级默认防护规则（防高危删除、防私钥泄露、防 API Token 泄露） |
