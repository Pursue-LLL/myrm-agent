import {
  ModeAdaptiveSuggestion,
  WorkMode,
  WorkspaceItem,
  WorkspaceThemeColor,
  WorkspaceVisualTheme,
} from './workspaceThemingTypes';

export interface ThemeColorClasses {
  bgClass: string;
  textClass: string;
  borderClass: string;
  ringClass: string;
  glowClass: string;
}

/**
 * 获取工作区自选主题色对应的 Tailwind 样式类映射
 */
export function getColorClasses(color: WorkspaceThemeColor): ThemeColorClasses {
  switch (color) {
    case 'violet':
      return {
        bgClass: 'bg-violet-500/10 dark:bg-violet-500/20',
        textClass: 'text-violet-600 dark:text-violet-400',
        borderClass: 'border-violet-500/30',
        ringClass: 'ring-violet-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(139,92,246,0.25)]',
      };
    case 'blue':
      return {
        bgClass: 'bg-blue-500/10 dark:bg-blue-500/20',
        textClass: 'text-blue-600 dark:text-blue-400',
        borderClass: 'border-blue-500/30',
        ringClass: 'ring-blue-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(59,130,246,0.25)]',
      };
    case 'emerald':
      return {
        bgClass: 'bg-emerald-500/10 dark:bg-emerald-500/20',
        textClass: 'text-emerald-600 dark:text-emerald-400',
        borderClass: 'border-emerald-500/30',
        ringClass: 'ring-emerald-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(16,185,129,0.25)]',
      };
    case 'amber':
      return {
        bgClass: 'bg-amber-500/10 dark:bg-amber-500/20',
        textClass: 'text-amber-600 dark:text-amber-400',
        borderClass: 'border-amber-500/30',
        ringClass: 'ring-amber-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(245,158,11,0.25)]',
      };
    case 'rose':
      return {
        bgClass: 'bg-rose-500/10 dark:bg-rose-500/20',
        textClass: 'text-rose-600 dark:text-rose-400',
        borderClass: 'border-rose-500/30',
        ringClass: 'ring-rose-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(244,63,94,0.25)]',
      };
    case 'indigo':
      return {
        bgClass: 'bg-indigo-500/10 dark:bg-indigo-500/20',
        textClass: 'text-indigo-600 dark:text-indigo-400',
        borderClass: 'border-indigo-500/30',
        ringClass: 'ring-indigo-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(99,102,241,0.25)]',
      };
    case 'slate':
    default:
      return {
        bgClass: 'bg-slate-500/10 dark:bg-slate-500/20',
        textClass: 'text-slate-600 dark:text-slate-400',
        borderClass: 'border-slate-500/30',
        ringClass: 'ring-slate-500/40',
        glowClass: 'shadow-[0_0_12px_rgba(100,116,139,0.25)]',
      };
  }
}

const STATIC_MODE_SUGGESTIONS: ModeAdaptiveSuggestion[] = [
  // 编程模式 (Coding)
  {
    id: 'sug-code-1',
    title: '针对当前模块执行整洁重构',
    mode: 'coding',
    category: '代码工程',
    prompt: '请严格按照单一职责与高内聚原则，对当前选中的核心函数执行重构，消除重复逻辑。',
  },
  {
    id: 'sug-code-2',
    title: '自动补齐关键路径高覆盖率单测',
    mode: 'coding',
    category: '质量门禁',
    prompt: '请为当前核心业务逻辑编写 Vitest 单元测试，覆盖边界异常与状态流转分支。',
  },
  {
    id: 'sug-code-3',
    title: '排查组件内存泄漏与无用重渲染',
    mode: 'coding',
    category: '性能调优',
    prompt: '请静态排查当前 React 组件中的闭包引用、未清理监听器及多余 State 触发。',
  },

  // 通用工作模式 (Work)
  {
    id: 'sug-work-1',
    title: '制作专业商业发布演示 PPT',
    mode: 'work',
    category: '商务办公',
    prompt: '请基于当前工作区背景，生成一份包含 10 页结构化大纲与演讲要点的商业发布演示文稿。',
  },
  {
    id: 'sug-work-2',
    title: '跨组会议纪要提取与待办指派',
    mode: 'work',
    category: '团队协同',
    prompt: '请分析粘贴的口语化会议速记，提炼决策共识并输出精准到人的 Action Items 待办矩阵。',
  },
  {
    id: 'sug-work-3',
    title: '商业服务合同合规红线审查',
    mode: 'work',
    category: '法务风控',
    prompt: '请逐条审查采购合同初稿，重点排查免责条款陷阱与违约赔偿上限漏洞。',
  },
];

/**
 * 获取当前工作模式自适应的快捷建议清单
 */
export function getModeAdaptiveSuggestions(
  mode: WorkMode,
): ModeAdaptiveSuggestion[] {
  return STATIC_MODE_SUGGESTIONS.filter((s) => s.mode === mode);
}

/**
 * 校验并规范化工作区主题
 */
export function validateWorkspaceTheme(
  theme?: Partial<WorkspaceVisualTheme>,
): WorkspaceVisualTheme {
  return {
    color: theme?.color ?? 'violet',
    icon: theme?.icon ?? 'code',
    customLabel: theme?.customLabel?.trim() || undefined,
  };
}

/**
 * 格式化工作区面包屑文案
 */
export function formatWorkspaceBreadcrumb(
  workspace: WorkspaceItem,
  mode: WorkMode,
): string {
  const modeLabel = mode === 'coding' ? '编程模式' : '通用办公模式';
  return `${workspace.name} · ${modeLabel}`;
}
