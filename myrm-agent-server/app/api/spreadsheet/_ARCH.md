# High-Aesthetic Styled Spreadsheet Generator & Multi-Office Sync Pipeline

## 架构定位

高颜值出版级电子表格渲染引擎、自动主题排版与多办公生态双向同步管道（HighAestheticStyledSpreadsheetGeneratorAndMultiOfficeSyncPipeline · Item 19）彻底解决传统 AI 导出裸 CSV / 粗糙表格的痛点，提供出版级美化 Excel 排版渲染引擎与多办公生态（飞书多维表格 Bitable / 企微文档 / 钉钉表格）一键同步管道。

## 模块清单

| 文件 | 职责 | 行数/规范 |
|---|---|---|
| `models.py` | Pydantic 数据契约：四大出版级商务主题枚举、列类型推断、行列结构、Excel 生成请求与多办公平台同步请求响应模型 | `< 120` 行，零 `Any` |
| `styled_excel_generator.py` | 出版级 OpenXML/Excel 渲染引擎：基于 openpyxl 实现表头主题色高亮加粗、斑马纹奇偶行变色、中文字符加权自适应列宽、首行冻结与千分位货币/百分比格式化 | `< 250` 行，零 `Any` |
| `routes.py` | FastAPI 路由控制器：提供 `POST /generate-excel`（流式文件下载）与 `POST /sync-office`（多办公生态一键分发） | `< 120` 行，零 `Any` |
| `__init__.py` | 包门面导出 `router` | 遵循子包规范 |
| `_ARCH.md` | 本子包架构说明与文件职责索引 | 遵循架构规范 |

## 核心特性

1. **四大出版级商务主题配色**：商务深蓝（`business_navy`）、现代黑金（`dark_gold`）、财务翡翠绿（`financial_emerald`）与科技石板灰（`tech_slate`）；
2. **自动化智能排版**：中文字符 2 宽度自适应列宽动态计算，首行大标题高对比横幅，第二行表头居中加粗，第三行及后续数据行斑马纹变色；
3. **视图锁定与格式化**：自动冻结 `A3` 窗格，显式保留网格线，数值千分位与百分比格式化；
4. **多办公生态一键分发**：无缝对接飞书 Bitable、企业微信与钉钉多维表格。
