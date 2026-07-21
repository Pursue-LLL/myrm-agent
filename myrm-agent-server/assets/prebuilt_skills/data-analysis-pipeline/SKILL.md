---
name: data-analysis-pipeline
description: >-
  Multi-agent data analysis pipeline: data collection, cleaning & validation,
  statistical analysis, visualization, and reporting. Parallel collection and
  cleaning followed by sequential analysis and delivery.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - data-analysis
  - visualization
  - statistics
  - multi-agent
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool web_search_tool
pipeline_spec:
  discovery_questions:
    - group: "data_info"
      group_label: "数据信息"
      questions:
        - id: "data_source"
          type: "text"
          label: "数据来源 (文件路径/数据库/API)"
        - id: "analysis_goal"
          type: "text"
          label: "分析目标 (想回答什么问题)"
        - id: "data_format"
          type: "select"
          label: "数据格式"
          options: ["CSV", "JSON", "Excel", "数据库查询", "API 接口", "混合来源"]
    - group: "output"
      group_label: "输出要求"
      questions:
        - id: "output_format"
          type: "select"
          label: "输出格式"
          options: ["交互式报告 (HTML)", "PDF 报告", "Jupyter Notebook", "Markdown 文档", "PPT 大纲"]
        - id: "chart_style"
          type: "select"
          label: "图表风格"
          options: ["商务简约", "学术严谨", "数据仪表盘", "信息图表"]
  role_templates:
    - role_id: "collector"
      description: "负责数据采集、格式转换和初步验证"
      required_skills: ["data-analysis", "web-scraping"]
    - role_id: "analyst"
      description: "负责数据清洗、统计分析和假设检验"
      required_skills: ["data-analysis"]
    - role_id: "visualizer"
      description: "负责图表设计、可视化制作和交互呈现"
      required_skills: ["data-analysis"]
    - role_id: "reporter"
      description: "负责报告撰写、结论提炼和建议输出"
      required_skills: ["data-analysis", "creative-ideation"]
  task_graph_seed:
    - title_template: "数据采集：{data_source}"
      description_template: "从{data_source}采集{data_format}格式数据，进行格式标准化和完整性初步验证"
      role: "collector"
      parents: []
    - title_template: "数据清洗与统计分析"
      description_template: "对采集数据进行清洗（缺失值、异常值、类型转换），然后围绕「{analysis_goal}」进行统计分析"
      role: "analyst"
      parents: [0]
    - title_template: "可视化制作：{chart_style}风格"
      description_template: "基于分析结果，以{chart_style}风格制作关键图表，回答「{analysis_goal}」"
      role: "visualizer"
      parents: [1]
    - title_template: "撰写分析报告（{output_format}）"
      description_template: "整合分析结论和图表，撰写{output_format}格式的完整报告，包含发现、建议和数据附录"
      role: "reporter"
      parents: [2]
contract:
  steps:
    - "Phase 1: Data Collection — acquire, validate, and standardize data"
    - "Phase 2: Analysis — clean data and perform statistical analysis"
    - "Phase 3: Visualization — create charts and interactive graphics"
    - "Phase 4: Reporting — synthesize findings into actionable report"
  success_criteria: "Actionable insights backed by rigorous analysis with professional visualizations"
  estimated_duration_seconds: 5400
---

# Data Analysis Pipeline

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

A structured pipeline for turning raw data into actionable insights. Each stage builds on the previous, ensuring data quality before analysis and clear communication of findings.

## How This Pipeline Works

1. **Data Collection** runs first — all subsequent steps depend on clean input
2. **Analysis** performs cleaning and statistical work
3. **Visualization** translates numbers into clear graphics
4. **Reporting** synthesizes everything into a deliverable

## Role Responsibilities

| Role | Focus Area | Key Deliverables |
|------|-----------|------------------|
| Collector | Data acquisition, format normalization | Clean dataset, data dictionary |
| Analyst | Statistical analysis, hypothesis testing | Analysis results, statistical summary |
| Visualizer | Chart design, interactive graphics | Chart set, dashboard layout |
| Reporter | Narrative, recommendations | Final report with executive summary |
