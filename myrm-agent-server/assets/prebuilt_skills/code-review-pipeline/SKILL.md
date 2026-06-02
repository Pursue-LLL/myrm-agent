---
name: code-review-pipeline
description: >-
  Multi-agent code review pipeline: static analysis, security audit, logic review,
  and fix verification. Creates a DAG with parallel security and logic passes
  followed by sequential fix and verification.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - code-review
  - security
  - quality
  - multi-agent
allowed-tools: file_read_tool grep_tool glob_tool bash_code_execute_tool
pipeline_spec:
  discovery_questions:
    - group: "review_scope"
      group_label: "审查范围"
      questions:
        - id: "target"
          type: "text"
          label: "审查目标 (文件路径/PR 链接/模块名)"
        - id: "review_focus"
          type: "multi-select"
          label: "审查重点"
          options: ["安全漏洞", "性能瓶颈", "代码质量", "架构设计", "测试覆盖", "并发安全"]
        - id: "language"
          type: "select"
          label: "主要语言"
          options: ["Python", "TypeScript/JavaScript", "Go", "Rust", "Java", "C/C++", "Mixed"]
    - group: "context"
      group_label: "上下文信息"
      questions:
        - id: "change_type"
          type: "select"
          label: "变更类型"
          options: ["新功能", "Bug修复", "重构", "性能优化", "依赖升级", "配置变更"]
        - id: "severity_threshold"
          type: "select"
          label: "最低报告级别"
          options: ["Critical Only", "High+", "Medium+", "All"]
  role_templates:
    - role_id: "analyzer"
      description: "负责静态分析、lint检查和代码度量"
      required_skills: ["code-review", "systematic-debugging"]
    - role_id: "security_reviewer"
      description: "负责安全审计、漏洞扫描和权限检查"
      required_skills: ["code-review"]
    - role_id: "logic_reviewer"
      description: "负责业务逻辑审查、边界条件和错误处理"
      required_skills: ["code-review", "systematic-debugging"]
    - role_id: "verifier"
      description: "负责修复验证、回归测试和最终确认"
      required_skills: ["test-driven-development"]
  task_graph_seed:
    - title_template: "静态分析：{target}"
      description_template: "对{target}进行{language}静态分析，检查代码度量、复杂度和lint问题"
      role: "analyzer"
      parents: []
    - title_template: "安全审计：{review_focus}"
      description_template: "针对{target}的{change_type}变更进行安全审计，重点关注{review_focus}相关漏洞"
      role: "security_reviewer"
      parents: []
    - title_template: "逻辑审查"
      description_template: "审查{target}的业务逻辑正确性、边界条件处理和错误恢复机制，报告级别{severity_threshold}"
      role: "logic_reviewer"
      parents: [0]
    - title_template: "修复验证与回归测试"
      description_template: "验证所有审查发现的问题修复，运行回归测试确保无新引入问题"
      role: "verifier"
      parents: [1, 2]
contract:
  steps:
    - "Phase 1: Static Analysis — automated code metrics and lint checks"
    - "Phase 2: Security Audit — vulnerability scanning (parallel with Phase 1)"
    - "Phase 3: Logic Review — business logic correctness and edge cases"
    - "Phase 4: Fix Verification — confirm fixes and run regression tests"
  success_criteria: "All critical/high issues resolved with verified fixes and no regressions"
  estimated_duration_seconds: 3600
---

# Code Review Pipeline

## Overview

A multi-agent code review pipeline that ensures comprehensive coverage by running specialized review passes in an optimized order. Security and static analysis run in parallel, followed by logic review and final verification.

## How This Pipeline Works

1. **Static Analysis** and **Security Audit** run in parallel — independent concerns
2. **Logic Review** depends on static analysis results (uses findings as context)
3. **Fix Verification** waits for both security and logic reviews to complete

## Role Responsibilities

| Role | Focus Area | Key Deliverables |
|------|-----------|------------------|
| Analyzer | Code metrics, complexity, lint | Static analysis report, complexity hotspots |
| Security Reviewer | Vulnerabilities, auth, injection | Security findings with severity ratings |
| Logic Reviewer | Correctness, edge cases, error handling | Logic issue report with fix suggestions |
| Verifier | Fix confirmation, regression testing | Verification report, test results |
