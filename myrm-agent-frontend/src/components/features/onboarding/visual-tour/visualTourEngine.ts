import type {
  ChecklistItem,
  ChecklistProgress,
  PlaygroundTemplate,
  SandboxExecutionPayload,
  SpotlightRect,
  TourStep,
} from './visualTourTypes';

export const DEFAULT_TOUR_STEPS: readonly TourStep[] = [
  {
    id: 'agent-switcher',
    title: '智能体分身快速切换',
    description: '顶部切换不同专业领域的 AI 协作专家，支持单聊与多智能体群组协同。',
    targetSelector: '[data-tour="agent-switcher"]',
    placement: 'bottom',
    actionLabel: '下一步',
    badgeText: '核心枢纽',
  },
  {
    id: 'skills-toolbox',
    title: '全能技能与连接器扩展',
    description: '通过 MCP 协议随时挂载终端执行、网页抓取与第三方外部自动化工具。',
    targetSelector: '[data-tour="skills-toolbox"]',
    placement: 'right',
    actionLabel: '了解工具',
    badgeText: '能力拓展',
  },
  {
    id: 'workbench-artifacts',
    title: '独立工件与实时变更对比',
    description: '右侧工作台实时查阅生成的代码、文档与文件差异对比，支持安全单文件撤销。',
    targetSelector: '[data-tour="workbench-artifacts"]',
    placement: 'left',
    actionLabel: '查看工作台',
    badgeText: '资产看板',
  },
  {
    id: 'model-tier-config',
    title: '极速响应与深度推理档位',
    description: '随时在 Turbo 极速与 Pro 深度推理档位间无缝切换，实现算力与性能最优化。',
    targetSelector: '[data-tour="model-tier-config"]',
    placement: 'top',
    actionLabel: '完成导览',
    badgeText: '模型路由',
  },
];

export const DEFAULT_CHECKLIST_ITEMS: readonly ChecklistItem[] = [
  {
    id: 'verify-model',
    title: '验证或接入首个语言模型',
    description: '系统已预置测试算力配额，点击即可测速并点亮首个模型通道。',
    actionUrl: '/settings/models',
    completed: false,
    required: true,
  },
  {
    id: 'create-agent-persona',
    title: '配置你的首位专属数字分身',
    description: '选择或定制适合你工作流的专业角色（如文案策划、代码架构师）。',
    actionUrl: '/agents',
    completed: false,
    required: true,
  },
  {
    id: 'run-first-task',
    title: '发起一次带文件产出的工作任务',
    description: '体验工件生成与实时预览，感受真实业务自动交付的闭环。',
    actionUrl: '/chat',
    completed: false,
    required: false,
  },
];

export const DEFAULT_PLAYGROUND_TEMPLATES: readonly PlaygroundTemplate[] = [
  {
    id: 'competitor-report',
    title: '竞品深度对比全景研报',
    description: '一键抓取并多维比对行业竞品，自动生成具备 SWOT 与落地策略的专业报表。',
    category: '商业分析',
    prompt: '请对当前市场上主流的前端性能监控系统进行多维对比分析，产出一份包含架构对比与选型建议的完整研报。',
    tags: ['竞品分析', 'SWOT', '自动化研报'],
    estimatedSeconds: 30,
  },
  {
    id: 'social-carousel',
    title: '爆款图文全景分镜轮播脚本',
    description: '根据主题提炼高完播率结构化文案，自动匹配分镜描述与视觉排版指南。',
    category: '内容创作',
    prompt: '请为“AI 原生工作流全景实战”设计一套 6 页高质量图文轮播脚本，包含抓人钩子、核心逻辑与行动倡议。',
    tags: ['文案分镜', '爆款排版', '社交媒体'],
    estimatedSeconds: 25,
  },
  {
    id: 'workspace-cleaner',
    title: '跨目录文件智能归类整理',
    description: '扫描目录资产并建立安全整理规划，生成变更 Diff 与可视化归档日志。',
    category: '效率工程',
    prompt: '请扫描当前工程下载临时目录，按文件类型与时间维度生成安全的整理方案，并输出拟迁移文件的清单对比。',
    tags: ['文件整理', '批处理', 'Diff预览'],
    estimatedSeconds: 40,
  },
];

export function calculateSpotlightRect(element: Element | null): SpotlightRect | null {
  if (!element) {
    return null;
  }

  const clientRect = element.getBoundingClientRect();
  return {
    top: Math.max(0, Math.round(clientRect.top)),
    left: Math.max(0, Math.round(clientRect.left)),
    width: Math.max(0, Math.round(clientRect.width)),
    height: Math.max(0, Math.round(clientRect.height)),
  };
}

export function calculateChecklistProgress(items: readonly ChecklistItem[]): ChecklistProgress {
  const totalCount = items.length;
  if (totalCount === 0) {
    return {
      completedCount: 0,
      totalCount: 0,
      percentage: 100,
      isAllCompleted: true,
    };
  }

  const completedCount = items.filter((item) => {
    return item.completed;
  }).length;

  const percentage = Math.round((completedCount / totalCount) * 100);
  const isAllCompleted = completedCount === totalCount;

  return {
    completedCount,
    totalCount,
    percentage,
    isAllCompleted,
  };
}

export function buildSandboxExecutionPayload(
  template: PlaygroundTemplate,
  userContext: Record<string, string> = {}
): SandboxExecutionPayload {
  let enrichedPrompt = template.prompt;
  const initialParams: Record<string, string> = { ...userContext };

  for (const [key, value] of Object.entries(userContext)) {
    if (value && value.trim().length > 0) {
      enrichedPrompt = `${enrichedPrompt}\n\n[附加上下文 ${key}]: ${value}`;
    }
  }

  return {
    prompt: enrichedPrompt,
    tags: template.tags,
    initialParams,
    templateId: template.id,
  };
}

export function getNextStepIndex(currentIndex: number, totalSteps: number): number {
  if (totalSteps <= 0) {
    return 0;
  }
  return Math.min(currentIndex + 1, totalSteps - 1);
}

export function getPrevStepIndex(currentIndex: number): number {
  return Math.max(0, currentIndex - 1);
}
