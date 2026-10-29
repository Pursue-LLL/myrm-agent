# pipeline/

## Overview
Agent Skills Evolution Pipeline module.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package |   Init   | — |
| frustration_detector.py | Core | Frustration signal detector. Zero-LLM regex detection of user style/format/workflow frustration signals (中英双语). Routes signals to DERIVED skill evolution. | ✅ |
| patch.py | Core | Patch application system for skill evolution. | ✅ |
| screener.py | Core | Evolution screening pipeline. Implements multi-phase checks including static error interception, GUI-First force retry, and LLM confirmation. LLM confirmation JSON parsed via `parse_llm_json_object` (robust against fences, prose, trailing commas). | ✅ |
| structured_extractor.py | Core | Provides SkillCaptureResult (with form routing: skill/cron_job/skip), StructuredExtractor. Raw JSON fallback extracts answer via `extract_answer_text` (兼容 reasoning 模型 content 空回退) and parses via `parse_llm_json_object` (robust against fences, prose, bare control chars, trailing commas). | ✅ |
| trace_analyzer.py | Core | Trace Analyzer for Skill Evolution. Provides progressive disclosure analysis. `analyze_slice` reads the `tool_start` / `tool_end` / `tool_failure` events the tool broadcaster persists (`args`, `result`, `error`) and returns a typed `SliceResult`; the slice goes to a model, so a call's arguments are clipped to 500 characters like its result and error. The failure-mode scan reads `tool_timeout` / `tool_failure`; a query for a type the logger never writes returns nothing and raises nothing, so `tests/architecture/test_event_queries_name_written_types.py` checks every `event_types=` literal. Includes `_extract_takeover_evidence()` to surface human takeover demonstrations as supplementary context for LLM-driven fixes. | ✅ |
| variant_generator.py | Core | Variant Generator with modular prompt assembly (editing principles, hard constraints, conservative editing, failure attribution, preference embedding, gene bank prior injection). Supports FIX/DERIVED content variants, preference-driven DERIVED variants, and OPTIMIZE_DESCRIPTION description-only variants. | ✅ |

## Key Dependencies

- `backends`
- `utils`
