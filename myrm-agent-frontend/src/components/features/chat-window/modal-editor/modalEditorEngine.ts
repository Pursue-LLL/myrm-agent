/**
 * [INPUT]
 * - @/components/features/chat-window/modal-editor/modalEditorTypes
 *
 * [OUTPUT]
 * - calculateEditorMetrics, BUILTIN_EDITOR_TEMPLATES, isTauriEnvironment, dispatchExternalEditorEvent
 *
 * [POS]
 * Pure computation engine for Item 196 (P1): PopoutFullscreenModalEditorAndDesktopBridgeSuite.
 * Analyzes word/char/line metrics, provides standardized writing templates,
 * and bridges desktop external editor events.
 */

import type {
  EditorTemplate,
  ModalEditorMetrics,
  ExternalEditorBridgePayload,
} from './modalEditorTypes';

export const BUILTIN_EDITOR_TEMPLATES: readonly EditorTemplate[] = [
  {
    id: 'prd-spec',
    name: '需求规范 PRD',
    description: '结构化产品需求文档，包含背景目标、功能边界与验收标准',
    content: `# [需求名称] 产品需求规范 (PRD)

## 1. 业务背景与目标
- **业务现状**：
- **核心目标**：
- **预期收益**：

## 2. 用户场景与痛点
- **目标用户**：
- **典型场景**：
- **当前痛点**：

## 3. 功能清单与交互边界
1. 功能点一：
2. 功能点二：

## 4. 非功能要求
- 性能要求：
- 安全与合规：

## 5. 验收标准
- [ ] 验收点 1
- [ ] 验收点 2
`,
  },
  {
    id: 'bug-diagnosis',
    name: '故障排查报告',
    description: '标准 Bug 现场与日志排查模版，便于 Agent 精准归因修复',
    content: `# [故障报告] 缺陷排查与诊断工单

## 1. 现象描述
- 异常摘要：
- 影响范围：

## 2. 复现步骤
1. 步骤一：
2. 步骤二：

## 3. 期望行为 vs 实际输出
- **期望**：
- **实际**：

## 4. 关键堆栈与日志
\`\`\`text
[粘贴报错日志或终端输出]
\`\`\`

## 5. 运行环境
- OS:
- Version / Runtime:
`,
  },
  {
    id: 'code-refactor',
    name: '架构重构方案',
    description: '模块与服务重构计划，包含动机、目标态与风险控制',
    content: `# [重构方案] 架构演进与技术债治理

## 1. 重构动机与现有坏味道
- 当前技术债：
- 性能/可维护性瓶颈：

## 2. 目标态架构设计
- 职责划分：
- 核心抽象与契约：

## 3. 分阶段迁移步骤
- [ ] Phase 1: 契约下沉与纯函数抽取
- [ ] Phase 2: 双门禁集成单测补齐
- [ ] Phase 3: 老逻辑平滑下线

## 4. 风险评估与回滚策略
- 关键风险：
- 应急预案：
`,
  },
  {
    id: 'doc-review',
    name: '公文方案润色',
    description: '通用办公材料与汇报总结框架，清晰阐述事实与论点',
    content: `# [公文材料] 综合汇报与方案草案

## 一、基本情况概述
[在此简明扼要陈述推进背景与当前阶段]

## 二、关键进展与成效
1. 重点事项一：
2. 重点事项二：

## 三、存在问题与风险分析
- 风险点：

## 四、下一步工作举措
- 计划安排：
`,
  },
];

export function calculateEditorMetrics(text: string): ModalEditorMetrics {
  const charCount = text.length;

  if (!text.trim()) {
    return {
      charCount: 0,
      wordCount: 0,
      lineCount: 0,
    };
  }

  // 匹配中文字符及英文单词进行综合词数统计
  const chineseChars = text.match(/[\u4e00-\u9fa5]/g) ?? [];
  const englishWords = text.match(/[a-zA-Z0-9_'-]+/g) ?? [];
  const wordCount = chineseChars.length + englishWords.length;

  const lines = text.split('\n');
  const lineCount = lines.length;

  return {
    charCount,
    wordCount,
    lineCount,
  };
}

export function isTauriEnvironment(): boolean {
  if (typeof window === 'undefined') {
    return false;
  }
  return '__TAURI__' in window || '__TAURI_INTERNALS__' in window;
}

export function dispatchExternalEditorEvent(payload: ExternalEditorBridgePayload): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const event = new CustomEvent('myrm:open-external-editor', {
      detail: payload,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    return true;
  } catch {
    return false;
  }
}
