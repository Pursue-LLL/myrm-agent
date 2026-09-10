# Office Document 技能实战避坑与自进化经验库 (EXPERIENCE.md)

> 本经验库遵循《技能内嵌经验库自闭环机制 (Embedded Experience Library Loop)》规范，由 Agent 执行实践中持续沉淀。
> 规范：在任务执行前优先检索吸收，任务遇新坑/修复后在此精炼追加。

---

### 【Excel / openpyxl】

#### 1. 合并单元格写入报错与数据丢失
- **触发场景**：向已存在的模板或新生成表格中的合并区域（MergedCell）写入数值或样式。
- **踩坑现象**：触发 `AttributeError: 'MergedCell' object has no attribute 'value'` 或数据静默丢失，仅首单元格保留。
- **根因分析**：openpyxl 的合并单元格仅左上角（Top-Left Anchor）是真正的 Cell 对象，其余从属格子是只读的 `MergedCell` 占位符。
- **最佳实践**：
  - 永远只向合并范围的左上角单元格（例如 `ws.cell(row=top, column=left).value = val`）写入数据；
  - 遍历单元格设置边框时，需针对合并区域内所有格子设置 Border，但值只能赋给锚点。

#### 2. 公式未计算与外部引用破损
- **触发场景**：生成包含 `=SUM(...)`, `=AVERAGE(...)` 的报表后立即在无头环境导出为 PDF 或供下游读取。
- **踩坑现象**：LibreOffice 导出的 PDF 中公式区域显示为 0 或 `#VALUE!`。
- **根因分析**：openpyxl 不内置公式求值引擎，仅将公式字符串写入 XML，不更新计算缓存值。
- **最佳实践**：
  - 必须使用大写公式名（`SUM` 而非 `sum`）；
  - 若需离线预览带值的表格，生成数据后使用 openpyxl 写入确定性初始求值结果，或在无头环境使用 `libreoffice --headless --convert-to pdf` 自动触发全表重算。

---

### 【PowerPoint / python-pptx】

#### 1. 文本框文字溢出与换行错乱
- **触发场景**：卡片式或双栏布局中生成超过 30 字的观点句或长说明。
- **踩坑现象**：文本垂直超出幻灯片底边或与其他图形发生穿透重叠。
- **根因分析**：python-pptx 默认创建的 TextFrame 不开启 `word_wrap=True`，或固定高度未预留多行排版间距。
- **最佳实践**：
  - 每个 TextFrame 创建后必须显式设置 `tf.word_wrap = True`；
  - 严格遵守反文字墙门禁：正文单条观点不超过 25 字，单张卡片不超过 3 行；
  - 必须留出至少 0.5 英寸的外边距（Padding）作为视觉呼吸区。

#### 2. 幻灯片图表伪造与非原生对象
- **触发场景**：需要展示季度营收走势或漏斗转化时，直接生成 HTML 截图贴入 PPT。
- **踩坑现象**：导出的 PPTX 无法二次编辑数据，缩放失真模糊。
- **根因分析**：试图偷懒将渲染后的图片插入幻灯片，破坏了商业 PPT 的可编辑性要求。
- **最佳实践**：
  - 必须使用 `from pptx.chart.data import CategoryChartData` 和 `prs.slides[i].shapes.add_chart()` 创建原生图表；
  - 数据必须作为 Series 结构化注入，确保使用者可在 PowerPoint 中右键“在 Excel 中编辑数据”。

---

### 【Word / python-docx】

#### 1. 表格列宽在部分 Office 客户端中默认折叠
- **触发场景**：在生成的 `.docx` 中插入多列表格并填入数据。
- **踩坑现象**：在 Microsoft Word 中打开正常，但在某些 WPS 或 Pages 预览中列宽粘连挤压。
- **根因分析**：python-docx 对 Table 设定的 `col_widths` 仅在单元格级（cell.width）有效，未设置全表列宽。
- **最佳实践**：
  - 设置列宽时必须双向同步：既在 `table.columns[i].width = Inches(w)` 设置，也在该列下的每个 `cell.width = Inches(w)` 设置；
  - 必须为表格设置明确的内边距样式（Padding）与自动换行属性。
