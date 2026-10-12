/**
 * [INPUT]
 * @/services/memory/curatorStudio::CuratedMemoryEntryDTO
 *
 * [OUTPUT]
 * FALLBACK_ENTRIES, FALLBACK_MARKDOWN: Default simulated data for offline/test environments.
 *
 * [POS]
 * Fallback fixture for Item 101 (HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite).
 * Strict typing applied: No `any` types allowed. Single file < 100 lines.
 */

import type { CuratedMemoryEntryDTO } from '@/services/memory/curatorStudio';

export const FALLBACK_ENTRIES: CuratedMemoryEntryDTO[] = [
  {
    entry_id: 'mem_pref_01',
    category: 'preference',
    title: '界面深色主题偏好',
    content: '用户明确偏好暗色界面与高对比度字体渲染，降低眼部疲劳。',
    confidence: 1.0,
    status: 'confirmed',
    tags: ['ui', 'theme', 'dark-mode'],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    entry_id: 'mem_fact_02',
    category: 'fact',
    title: '前端架构技术栈',
    content: '项目采用 React 19 + TailwindCSS v4 + Vite + Bun 全栈工具链。',
    confidence: 0.95,
    status: 'confirmed',
    tags: ['frontend', 'react19', 'bun'],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    entry_id: 'mem_proc_03',
    category: 'procedure',
    title: '生产发布门禁规范',
    content: '发布前必须全量通过 Lint、Vitest 与 a11y ratchet 0 违规检测。',
    confidence: 1.0,
    status: 'confirmed',
    tags: ['ci', 'pipeline', 'a11y'],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
  {
    entry_id: 'mem_gate_04',
    category: 'preference',
    title: '夜间免打扰模式推断',
    content: 'AI 自发推断：用户可能偏好在 22:00 后静音非紧急系统通知。',
    confidence: 0.72,
    status: 'pending_confirmation',
    tags: ['notification', 'night-mode'],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

export const FALLBACK_MARKDOWN = `---
title: Workspace Memory Mirror
schema_version: '1.0'
updated_at: '2026-10-08T05:00:00Z'
total_entries: 4
---

# Workspace Memory Mirror

> Note: This file is a bi-directional mirror of your AI Assistant's memory.
> You can directly edit, delete, or add memory items here.

## Preferences
- [x] **界面深色主题偏好** (id: mem_pref_01, confidence: 1.00): 用户明确偏好暗色界面与高对比度字体渲染，降低眼部疲劳。 tags: [ui, theme, dark-mode]
- [ ] **夜间免打扰模式推断** (id: mem_gate_04, confidence: 0.72): AI 自发推断：用户可能偏好在 22:00 后静音非紧急系统通知。 tags: [notification, night-mode]

## Facts
- [x] **前端架构技术栈** (id: mem_fact_02, confidence: 0.95): 项目采用 React 19 + TailwindCSS v4 + Vite + Bun 全栈工具链。 tags: [frontend, react19, bun]

## Procedures
- [x] **生产发布门禁规范** (id: mem_proc_03, confidence: 1.00): 发布前必须全量通过 Lint、Vitest 与 a11y ratchet 0 违规检测。 tags: [ci, pipeline, a11y]
`;
