# api/media/

## 架构概述

图片/视频等媒体生成 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | Media gallery API routes. | ✅ |
| `batch_routes.py` | 路由 | Batch image generation API — create, control, monitor batch jobs. | ✅ |
| `router.py` | 路由 | Media gallery API — list, search, tag, serve, delete media items. | ✅ |
