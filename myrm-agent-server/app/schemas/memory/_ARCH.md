# app/schemas/memory 模块架构

记忆域共享 Pydantic DTO。api 与 services 层共用，不含 HTTP 路由逻辑。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `crud.py` | 核心 | Memory CRUD、偏好、评分、导出请求/响应模型 | ✅ |
| `archive.py` | 核心 | 归档、导入、回滚请求/响应模型 | ✅ |
| `command_center.py` | 核心 | Memory Command Center 仪表盘 DTO | ✅ |
