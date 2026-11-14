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

/** `auto` leaves the depth to the model; `off` asks for no thinking; the others ask for that depth. */
export type ThinkingEffortLevel = 'auto' | 'off' | 'low' | 'medium' | 'high' | 'max';

export interface ThinkingBudgetTierConfig {
  level: ThinkingEffortLevel;
  labelKey: string;
  tokenBudget: number;
  /** Budget shown on the slider; null for `auto`, which has no fixed budget and shows its `labelKey` text. */
  tokenLabel: string | null;
  /** `thinkingPermission` message key of the one-line latency/use-case hint. */
  latencyDescriptionKey: string;
  reasoningEffort?: 'low' | 'medium' | 'high';
  colorClass: string;
  activeColorClass: string;
}

export const THINKING_BUDGET_TIERS: readonly ThinkingBudgetTierConfig[] = [
  {
    level: 'auto',
    labelKey: 'thinkingTierAuto',
    tokenBudget: 0,
    tokenLabel: null,
    latencyDescriptionKey: 'thinkingTierAutoLatency',
    reasoningEffort: undefined,
    colorClass: 'bg-primary/50',
    activeColorClass: 'text-muted-foreground',
  },
  {
    level: 'off',
    labelKey: 'thinkingTierOff',
    tokenBudget: 0,
    tokenLabel: '0k',
    latencyDescriptionKey: 'thinkingTierOffLatency',
    reasoningEffort: undefined,
    colorClass: 'bg-slate-400',
    activeColorClass: 'text-slate-500 dark:text-slate-400',
  },
  {
    level: 'low',
    labelKey: 'thinkingTierLow',
    tokenBudget: 2048,
    tokenLabel: '2k',
    latencyDescriptionKey: 'thinkingTierLowLatency',
    reasoningEffort: 'low',
    colorClass: 'bg-sky-400',
    activeColorClass: 'text-sky-500 dark:text-sky-400',
  },
  {
    level: 'medium',
    labelKey: 'thinkingTierMedium',
    tokenBudget: 8192,
    tokenLabel: '8k',
    latencyDescriptionKey: 'thinkingTierMediumLatency',
    reasoningEffort: 'medium',
    colorClass: 'bg-amber-400',
    activeColorClass: 'text-amber-500 dark:text-amber-400',
  },
  {
    level: 'high',
    labelKey: 'thinkingTierHigh',
    tokenBudget: 16384,
    tokenLabel: '16k',
    latencyDescriptionKey: 'thinkingTierHighLatency',
    reasoningEffort: 'high',
    colorClass: 'bg-orange-500',
    activeColorClass: 'text-orange-500 dark:text-orange-400',
  },
  {
    level: 'max',
    labelKey: 'thinkingTierMax',
    tokenBudget: 32768,
    tokenLabel: '32k',
    latencyDescriptionKey: 'thinkingTierMaxLatency',
    reasoningEffort: 'high',
    colorClass: 'bg-rose-500',
    activeColorClass: 'text-rose-500 dark:text-rose-400',
  },
] as const;

export type PermissionTier = 'strict' | 'semi-auto' | 'full-auto';

export interface PermissionTierConfig {
  tier: PermissionTier;
  /** `thinkingPermission` message key of the tier's short name. */
  labelKey: string;
  /** `thinkingPermission` message key of the tier's one-line description. */
  descriptionKey: string;
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
    descriptionKey: 'permissionTierStrictDesc',
    allowsAutoFileEdit: false,
    allowsAutoSafeShell: false,
    colorClass: 'text-sky-600 dark:text-sky-400',
    borderColorClass: 'border-sky-500/30',
    badgeBgClass: 'bg-sky-500/10',
  },
  'semi-auto': {
    tier: 'semi-auto',
    labelKey: 'permissionTierSemiAuto',
    descriptionKey: 'permissionTierSemiAutoDesc',
    allowsAutoFileEdit: true,
    allowsAutoSafeShell: true,
    colorClass: 'text-amber-600 dark:text-amber-400',
    borderColorClass: 'border-amber-500/30',
    badgeBgClass: 'bg-amber-500/10',
  },
  'full-auto': {
    tier: 'full-auto',
    labelKey: 'permissionTierFullAuto',
    descriptionKey: 'permissionTierFullAutoDesc',
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
  reason:
    | 'strict_mode_requires_approval'
    | 'semi_auto_code_safe_allowed'
    | 'semi_auto_safe_command_allowed'
    | 'semi_auto_high_risk_intercepted'
    | 'full_auto_yolo_allowed';
  message: string;
}
