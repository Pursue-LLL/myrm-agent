# Bitable & Spreadsheet Sidebar Interactive CoPilot

`app/services/bitable_copilot/` 提供了多维表格（飞书多维表格 Bitable / Airtable / 本地 Excel 视图）的原生嵌入式交互分析伴侣。

## 模块清单
| 文件 | 类型 | 职责说明 | 状态 |
| --- | --- | --- | --- |
| `models.py` | 核心模型 | 定义表格字段 Schema、行数据、上下文载荷与单元格 Diff 变更提案 | ✅ |
| `engine.py` | 核心引擎 | 提供目标字段自动推断、跨行批量 AI 加工与生成结果结构化提取 | ✅ |
