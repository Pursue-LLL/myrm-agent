import { create } from 'zustand';
import type {
  ClarificationAnswers,
  ClarificationGateState,
  ClarificationQuestion,
  ClarificationSourceMode,
  GoalSpec,
} from './clarificationGateTypes';

const AMBIGUOUS_INTENT_KEYWORDS = [
  '构建',
  '做个',
  '开发',
  '设计',
  '重构',
  '实现一个',
  '落地页',
  '系统',
  '全套方案',
  '宣传页',
  '同步脚本',
  'create a',
  'build a',
  'make an app',
  'landing page',
];

const DEFAULT_QUESTIONS: ClarificationQuestion[] = [
  {
    id: 'q_platform',
    title: '目标运行环境与平台',
    subtitle: '界定交付物运行的目标宿主',
    isMultiSelect: false,
    options: [
      { id: 'web', label: 'Web 前端与现代化浏览器', isRecommended: true },
      { id: 'desktop', label: 'Tauri / 跨平台桌面客户端' },
      { id: 'server', label: 'Node.js / Python 后端服务' },
      { id: 'spec_only', label: '仅输出技术方案与规格架构设计' },
    ],
  },
  {
    id: 'q_deliverable',
    title: '期望交付产物深度',
    subtitle: '避免生成玩具级 Demo 或过度设计',
    isMultiSelect: true,
    options: [
      { id: 'runnable_code', label: '包含完整单测与工业级类型标注的可运行代码', isRecommended: true },
      { id: 'api_contract', label: '前后端标准接口契约与数据模型定义' },
      { id: 'ui_mockup', label: '高审美交互式 UI 组件与响应式样式' },
      { id: 'step_guide', label: '分步落地指引与排障手册' },
    ],
  },
  {
    id: 'q_architecture_style',
    title: '架构风格与工程约束',
    subtitle: '决定系统复杂度与依赖选型',
    isMultiSelect: false,
    options: [
      { id: 'minimal_perf', label: '极简高性能（零冗余依赖，原生纯粹，严控体积）', isRecommended: true },
      { id: 'enterprise_robust', label: '企业级防御性架构（全面校验、重试熔断与日志审计）' },
      { id: 'fast_prototype', label: '快速验证 MVP（最短路径打通核心流程）' },
    ],
  },
];

export function detectAmbiguity(text: string): boolean {
  const trimmed = text.trim();
  if (!trimmed) {
    return false;
  }
  if (trimmed.toLowerCase().includes('/grill-me')) {
    return true;
  }
  if (trimmed.length > 40) {
    return false;
  }
  const lower = trimmed.toLowerCase();
  return AMBIGUOUS_INTENT_KEYWORDS.some((kw) => lower.includes(kw));
}

function getDefaultAnswers(questions: ClarificationQuestion[]): ClarificationAnswers {
  const initial: ClarificationAnswers = {};
  for (const q of questions) {
    const recommended = q.options.find((opt) => opt.isRecommended) ?? q.options[0];
    if (recommended) {
      initial[q.id] = [recommended.id];
    } else {
      initial[q.id] = [];
    }
  }
  return initial;
}

interface ClarificationGateActions {
  checkAndOpen: (input: string, mode?: ClarificationSourceMode) => boolean;
  openGate: (input: string, mode: ClarificationSourceMode) => void;
  closeGate: () => void;
  toggleOption: (questionId: string, optionId: string, isMulti: boolean) => void;
  setCustomNotes: (notes: string) => void;
  skipClarification: () => GoalSpec;
  compileGoalSpec: () => GoalSpec;
  resetState: () => void;
}

export type ClarificationGateStore = ClarificationGateState & ClarificationGateActions;

export const useClarificationGateStore = create<ClarificationGateStore>((set, get) => ({
  isOpen: false,
  rawInput: '',
  sourceMode: 'auto',
  questions: DEFAULT_QUESTIONS,
  answers: getDefaultAnswers(DEFAULT_QUESTIONS),
  customNotes: '',
  compiledSpec: null,

  checkAndOpen: (input: string, mode: ClarificationSourceMode = 'auto') => {
    if (detectAmbiguity(input)) {
      get().openGate(input, mode);
      return true;
    }
    return false;
  },

  openGate: (rawInput: string, sourceMode: ClarificationSourceMode) => {
    const cleanPrompt = rawInput.replace(/\/grill-me/gi, '').trim();
    set({
      isOpen: true,
      rawInput: cleanPrompt || rawInput,
      sourceMode,
      answers: getDefaultAnswers(DEFAULT_QUESTIONS),
      customNotes: '',
      compiledSpec: null,
    });
  },

  closeGate: () => {
    set({ isOpen: false });
  },

  toggleOption: (questionId: string, optionId: string, isMulti: boolean) => {
    const state = get();
    const current = state.answers[questionId] ?? [];
    let updated: string[];

    if (isMulti) {
      if (current.includes(optionId)) {
        updated = current.filter((id) => id !== optionId);
        // 确保至少保留一项
        if (updated.length === 0) {
          updated = [optionId];
        }
      } else {
        updated = [...current, optionId];
      }
    } else {
      updated = [optionId];
    }

    set({
      answers: {
        ...state.answers,
        [questionId]: updated,
      },
    });
  },

  setCustomNotes: (customNotes: string) => {
    set({ customNotes });
  },

  skipClarification: () => {
    const state = get();
    const cleanPrompt = state.rawInput.trim();

    const spec: GoalSpec = {
      rawPrompt: cleanPrompt,
      goalSummary: `自动根据缺省假设启动任务: ${cleanPrompt}`,
      targetPlatform: 'Web 现代化浏览器（模型缺省假定）',
      deliverables: ['可直接运行的完整工程代码（模型缺省假定）'],
      constraints: ['采用极简高性能无依赖原则（模型缺省假定）'],
      assumptionsByModel: [
        '用户显式选择跳过深度澄清提问；',
        '系统默认采用 Web 前端 + 极简高性能架构标准推进；',
        '如需特殊依赖或宿主调整，可在后续交互中单项纠偏。',
      ],
      isSkippedByUser: true,
      compiledPrompt: `[Goal Spec (用户已跳过澄清 - 采用模型稳健假设)]
原始需求: ${cleanPrompt}
技术假定: 现代 Web / 极简高性能 / 完整交付物
请以稳健工程规范开始执行，并在首轮回复明确说明所采用的关键默认假设。`,
    };

    set({
      compiledSpec: spec,
      isOpen: false,
    });

    return spec;
  },

  compileGoalSpec: () => {
    const state = get();
    const cleanPrompt = state.rawInput.trim();

    // 解析已选选项标签
    const selectedLabels: Record<string, string[]> = {};
    for (const q of state.questions) {
      const selectedIds = state.answers[q.id] ?? [];
      selectedLabels[q.id] = q.options
        .filter((opt) => selectedIds.includes(opt.id))
        .map((opt) => opt.label);
    }

    const platform = selectedLabels['q_platform']?.[0] ?? 'Web 前端与现代化浏览器';
    const deliverables = selectedLabels['q_deliverable'] ?? ['可运行代码与单测'];
    const styleConstraint = selectedLabels['q_architecture_style']?.[0] ?? '极简高性能';

    const constraints = [
      `架构偏好: ${styleConstraint}`,
      ...(state.customNotes.trim() ? [`用户补充要求: ${state.customNotes.trim()}`] : []),
    ];

    const compiledPrompt = `[Goal Spec · 无歧义目标规格书]
🎯 核心目标: ${cleanPrompt}
🖥️ 运行平台: ${platform}
📦 预期交付物:
${deliverables.map((d) => `  - ${d}`).join('\n')}
🛡️ 核心约束与风格:
${constraints.map((c) => `  - ${c}`).join('\n')}

请以此无歧义 Goal Spec 为最高执行准则，严格遵照上述范围与产物规范启动执行。`;

    const spec: GoalSpec = {
      rawPrompt: cleanPrompt,
      goalSummary: `已对齐规格的目标: ${cleanPrompt}`,
      targetPlatform: platform,
      deliverables,
      constraints,
      assumptionsByModel: ['所有关键维度均经由人类结构化拍板确认，无模型私自假设。'],
      isSkippedByUser: false,
      compiledPrompt,
    };

    set({
      compiledSpec: spec,
      isOpen: false,
    });

    return spec;
  },

  resetState: () => {
    set({
      isOpen: false,
      rawInput: '',
      sourceMode: 'auto',
      questions: DEFAULT_QUESTIONS,
      answers: getDefaultAnswers(DEFAULT_QUESTIONS),
      customNotes: '',
      compiledSpec: null,
    });
  },
}));
