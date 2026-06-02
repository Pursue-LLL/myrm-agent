---
name: research-paper-pipeline
description: >-
  Academic research paper writing pipeline: literature survey, outline drafting,
  section writing, integration review, and reference formatting. Multi-agent DAG
  for efficient scholarly output.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - research
  - academic
  - writing
  - multi-agent
allowed-tools: file_read_tool file_write_tool web_search_tool bash_code_execute_tool
pipeline_spec:
  discovery_questions:
    - group: "paper_info"
      group_label: "论文信息"
      questions:
        - id: "topic"
          type: "text"
          label: "论文题目/研究方向"
        - id: "paper_type"
          type: "select"
          label: "论文类型"
          options: ["综述 (Survey/Review)", "实验研究 (Empirical)", "理论分析 (Theoretical)", "系统设计 (System Design)", "案例研究 (Case Study)"]
        - id: "target_venue"
          type: "text"
          label: "目标期刊/会议 (可选)"
    - group: "scope"
      group_label: "范围与要求"
      questions:
        - id: "word_count"
          type: "select"
          label: "目标篇幅"
          options: ["3000-5000 词 (短文)", "5000-8000 词 (标准)", "8000-12000 词 (长文)", "12000+ 词 (专著级)"]
        - id: "language"
          type: "select"
          label: "写作语言"
          options: ["English", "中文", "日本語"]
        - id: "citation_style"
          type: "select"
          label: "引用格式"
          options: ["APA 7th", "IEEE", "ACM", "Chicago", "GB/T 7714"]
  role_templates:
    - role_id: "researcher"
      description: "负责文献调研、数据库检索和研究现状梳理"
      required_skills: ["deep-research", "arxiv-research"]
    - role_id: "writer"
      description: "负责大纲拟定和各章节撰写"
      required_skills: ["creative-ideation"]
    - role_id: "integrator"
      description: "负责全文整合审校、逻辑一致性检查"
      required_skills: ["code-review"]
    - role_id: "formatter"
      description: "负责参考文献格式化和排版规范"
      required_skills: ["data-analysis"]
  task_graph_seed:
    - title_template: "文献调研：{topic}"
      description_template: "检索{topic}相关的高引用文献，梳理研究现状和关键发现，为{paper_type}提供充分的理论基础"
      role: "researcher"
      parents: []
    - title_template: "拟定论文大纲"
      description_template: "基于文献调研结果，为{word_count}的{paper_type}拟定详细大纲，确保逻辑连贯"
      role: "writer"
      parents: [0]
    - title_template: "撰写各章节"
      description_template: "按大纲完成{topic}论文各章节的{language}写作，目标篇幅{word_count}"
      role: "writer"
      parents: [1]
    - title_template: "全文整合审校"
      description_template: "检查全文逻辑一致性、论证严密性和语言质量，确保符合{target_venue}的学术标准"
      role: "integrator"
      parents: [2]
    - title_template: "参考文献格式化（{citation_style}）"
      description_template: "按{citation_style}格式整理所有参考文献，检查引用完整性和格式规范"
      role: "formatter"
      parents: [3]
contract:
  steps:
    - "Phase 1: Literature Survey — comprehensive search and synthesis of prior work"
    - "Phase 2: Outline — logical structure and argument flow design"
    - "Phase 3: Writing — section-by-section composition"
    - "Phase 4: Integration Review — coherence, rigor, and quality check"
    - "Phase 5: Reference Formatting — citation style compliance"
  success_criteria: "Complete paper with rigorous arguments, proper citations, and publication-ready formatting"
  estimated_duration_seconds: 14400
---

# Research Paper Pipeline

## Overview

A structured pipeline for academic paper writing that ensures thoroughness at every stage. Each phase builds on the previous one, guaranteeing a coherent final output.

## How This Pipeline Works

1. **Literature Survey** runs first — everything else depends on knowing the field
2. **Outline** crystallizes the argument structure
3. **Section Writing** fills in the content
4. **Integration Review** ensures quality and consistency
5. **Reference Formatting** handles the final polish

## Role Responsibilities

| Role | Focus Area | Key Deliverables |
|------|-----------|------------------|
| Researcher | Literature search, gap analysis | Annotated bibliography, research landscape map |
| Writer | Structure design, composition | Outline, full draft sections |
| Integrator | Quality assurance, coherence | Revision notes, consistency report |
| Formatter | Citation management, typesetting | Formatted reference list, style compliance report |
