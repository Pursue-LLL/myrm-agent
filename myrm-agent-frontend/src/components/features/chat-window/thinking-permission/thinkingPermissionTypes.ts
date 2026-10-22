/**
 * [INPUT]
 * - None (pure TypeScript contract & configuration constants)
 *
 * [OUTPUT]
 * - ThinkingEffortLevel, PermissionTier types
 * - THINKING_BUDGET_TIERS, PERMISSION_TIER_CONFIGS configs
 * - HIGH_RISK_SHELL_PATTERNS, isHighRiskCommand validation helper
 *
 * [POS]
 * Defines runtime contracts for the Thinking Budget Effort Slider and 3-Tier
 * Permission Mode Switcher in the chat window, preventing arbitrary string errors.
 */

export type ThinkingEffortLevel = 'off' | 'low' | 'medium' | 'high' | 'max';

export interface ThinkingBudgetTierConfig {
  level: ThinkingEffortLevel;
  labelKey: string;
  tokenBudget: number;
  tokenLabel: string;
  latencyDescription: string;
  reasoningEffort?: 'low' | 'medium' | 'high';
  colorClass: string;
  activeColorClass: string;
}

export const THINKING_BUDGET_TIERS: readonly ThinkingBudgetTierConfig[] = [
  {
    level: 'off',
    labelKey: 'thinkingTierOff',
    tokenBudget: 0,
    tokenLabel: '0k',
    latencyDescription: '直出作答，无思维开销',
    reasoningEffort: undefined,
    colorClass: 'bg-slate-400',
    activeColorClass: 'text-slate-500 dark:text-slate-400',
  },
  {
    level: 'low',
    labelKey: 'thinkingTierLow',
    tokenBudget: 2048,
    tokenLabel: '2k',
    latencyDescription: '轻量思考，适合简单润色与解释',
    reasoningEffort: 'low',
    colorClass: 'bg-sky-400',
    activeColorClass: 'text-sky-500 dark:text-sky-400',
  },
  {
    level: 'medium',
    labelKey: 'thinkingTierMedium',
    tokenBudget: 8192,
    tokenLabel: '8k',
    latencyDescription: '平衡思考，适合常规多步逻辑推理',
    reasoningEffort: 'medium',
    colorClass: 'bg-amber-400',
    activeColorClass: 'text-amber-500 dark:text-amber-400',
  },
  {
    level: 'high',
    labelKey: 'thinkingTierHigh',
    tokenBudget: 16384,
    tokenLabel: '16k',
    latencyDescription: '深度思考，适合复杂算法与系统设计',
    reasoningEffort: 'high',
    colorClass: 'bg-orange-500',
    activeColorClass: 'text-orange-500 dark:text-orange-400',
  },
  {
    level: 'max',
    labelKey: 'thinkingTierMax',
    tokenBudget: 32768,
    tokenLabel: '32k',
    latencyDescription: '极限推理，适合深层严密数理与全景架构',
    reasoningEffort: 'high',
    colorClass: 'bg-rose-500',
    activeColorClass: 'text-rose-500 dark:text-rose-400',
  },
] as const;

export type PermissionTier = 'strict' | 'semi-auto' | 'full-auto';

export interface PermissionTierConfig {
  tier: PermissionTier;
  labelKey: string;
  shortLabel: string;
  description: string;
  allowsAutoFileEdit: boolean;
  allowsAutoSafeShell: boolean;
  colorClass: string;
  borderColorClass: string;
  badgeBgClass: string;
}

export const PERMISSION_TIER_CONFIGS: Record<PermissionTier, PermissionTierConfig> = {
  strict: {
    tier: 'strict',
    labelKey: 'permissionTierStrict',
    shortLabel: '安全守护',
    description: '所有文件修改与 Shell 执行均需人工显式审批',
    allowsAutoFileEdit: false,
    allowsAutoSafeShell: false,
    colorClass: 'text-sky-600 dark:text-sky-400',
    borderColorClass: 'border-sky-500/30',
    badgeBgClass: 'bg-sky-500/10',
  },
  'semi-auto': {
    tier: 'semi-auto',
    labelKey: 'permissionTierSemiAuto',
    shortLabel: '半自动敏捷',
    description: '自动放行常规代码编辑与安全命令，高危命令强制拦截审批',
    allowsAutoFileEdit: true,
    allowsAutoSafeShell: true,
    colorClass: 'text-amber-600 dark:text-amber-400',
    borderColorClass: 'border-amber-500/30',
    badgeBgClass: 'bg-amber-500/10',
  },
  'full-auto': {
    tier: 'full-auto',
    labelKey: 'permissionTierFullAuto',
    shortLabel: '全自动无人值守',
    description: '受控在沙箱边界内全速自主执行，零弹窗秒级流转',
    allowsAutoFileEdit: true,
    allowsAutoSafeShell: true,
    colorClass: 'text-emerald-600 dark:text-emerald-400',
    borderColorClass: 'border-emerald-500/30',
    badgeBgClass: 'bg-emerald-500/10',
  },
};

export const HIGH_RISK_SHELL_PATTERNS: readonly RegExp[] = [
  /\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?|--recursive)\b/i,
  /\brm\s+(-[a-zA-Z]*f[a-zA-Z]*r?)\b/i,
  /\bsudo\b/i,
  /\bchmod\s+(-R\s+)?(777|000)\b/i,
  /\bchown\s+-R\b/i,
  /\b(curl|wget)\b.*\|\s*(sh|bash|zsh)\b/i,
  /\b(mkfs|dd\s+if=)\b/i,
  /\bkill\s+-9\b/i,
  /\b(shutdown|reboot|init\s+0)\b/i,
  /\b(truncate|shred)\b/i,
  /\b(drop\s+database|truncate\s+table)\b/i,
] as const;

export function isHighRiskCommand(command: string): boolean {
  if (!command || !command.trim()) {
    return false;
  }
  const normalized = command.trim();
  for (const pattern of HIGH_RISK_SHELL_PATTERNS) {
    if (pattern.test(normalized)) {
      return true;
    }
  }
  return false;
}

export interface PermissionCheckResult {
  approved: boolean;
  reason: 'strict_mode_requires_approval' | 'semi_auto_code_safe_allowed' | 'semi_auto_safe_command_allowed' | 'semi_auto_high_risk_intercepted' | 'full_auto_yolo_allowed';
  message: string;
}
