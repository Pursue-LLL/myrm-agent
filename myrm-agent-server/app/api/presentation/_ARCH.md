# Presentation API Module Architecture

## 架构定位

企业级高保真 PPT 演示文稿生成引擎与多模态概念生图图解套件后端服务（Enterprise Presentation Slide Generator And Visual Concept Illustrator · Item 16）。通过结构化大纲生成与基于 `python-pptx` 的高保真矢量模版引擎，支持企业标准宽屏 (16:9) 幻灯片排版、多栏对比卡片、里程碑步骤矩阵、AI 概念生图图解与无损二进制 `.pptx` 导出下载。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `models.py` | Pydantic 数据模型：幻灯片版式、元素结构、生成请求与工件响应模型 | `< 100` 行，严格类型提示 |
| `pptx_generator.py` | 幻灯片大纲推导与 `python-pptx` 矢量渲染引擎，支持 4 大主题配色与 16:9 母版排版 | `< 300` 行，原生 PowerPoint 矢量形状 |
| `routes.py` | FastAPI 路由：`POST /generate`、`GET /{id}` 与 `GET /{id}/download` 二进制流式导出 | `< 120` 行，遵循 RESTful 规范 |
| `__init__.py` | 统一导出 APIRouter | 门面规范 |
| `_ARCH.md` | 本模块架构说明与职责索引 | 遵循架构规范 |

## 核心特性

1. **高保真矢量排版**：绝非截图转换，全部采用原生 PowerPoint 矩形、文本框与矢量配色，支持 Office/WPS 任意二次编辑；
2. **多主题配色方案**：内置 `enterprise_blue`、`minimal_dark`、`creative_gradient`、`tech_emerald` 等专业企业母版；
3. **多模态概念图解**：支持生成概念插图占位与提示词，提升视觉冲击力；
4. **内存安全与即时流式导出**：生成文件即时缓冲流式下载，支持端到端预览与分享。
