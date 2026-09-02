/**
 * [INPUT]
 * - @/services/cron::createCronJob, triggerCronJob (POS: Cron 任务创建与触发客户端)
 * - @/store/useChatStore (POS: 活跃聊天与 Agent 状态)
 * - @/store/useConfigStore (POS: 模型与个人配置)
 * - @/services/i18nToastService::showI18nToast (POS: i18n toast 封装)
 *
 * [OUTPUT]
 * - parseNaturalInterval: 自然语言时间解析函数 (中英文单位支持，下限 60,000ms)
 * - parseLoopCommandInput: /loop 命令入参解析函数 -> { intervalMs, prompt }
 * - executeLoopSlashCommand: 执行 /loop slash 命令创建周期任务并即时首跑
 *
 * [POS]
 * 原生 /loop Slash 命令执行与调度解析服务。供 builtinActions 与输入框交互复用。
 */

import { showI18nToast } from '@/services/i18nToastService';
import type { ActionResult } from '@/types/command';

export const DEFAULT_LOOP_INTERVAL_MS = 600_000; // 10m
export const MIN_LOOP_INTERVAL_MS = 60_000; // 1m

/**
 * 解析中英文自然语言时间间隔为毫秒数 (最小 1 分钟，防溢出)
 */
export function parseNaturalInterval(
  text: string,
  defaultMs: number = DEFAULT_LOOP_INTERVAL_MS,
): number {
  const cleaned = text.trim().toLowerCase();
  if (!cleaned) {
    return defaultMs;
  }

  if (cleaned === '每天' || cleaned === '每日' || cleaned === 'daily' || cleaned === 'day') {
    return 86_400_000;
  }

  const normalized = cleaned.replace(/^(?:every|each|每隔|每)\s*/i, '').trim();

  if (normalized === '半小时' || normalized === '半个小时' || normalized === '半个钟头') {
    return 1_800_000;
  }
  if (
    normalized === '1个半小时' ||
    normalized === '一个半小时' ||
    normalized === '1.5h' ||
    normalized === '1.5小时'
  ) {
    return 5_400_000;
  }
  if (
    normalized === '每天' ||
    normalized === '每日' ||
    normalized === '天' ||
    normalized === 'day' ||
    normalized === 'daily'
  ) {
    return 86_400_000;
  }

  const pattern =
    /^(\d+)\s*(s|sec|secs|second|seconds|秒|秒钟|m|min|mins|minute|minutes|分|分钟|h|hr|hrs|hour|hours|个?小时|个?钟头|d|day|days|天)?$/i;
  const match = normalized.match(pattern);
  if (!match) {
    return defaultMs;
  }

  const val = parseInt(match[1], 10);
  if (Number.isNaN(val) || val <= 0) {
    return defaultMs;
  }

  const unit = (match[2] || 'm').toLowerCase();

  let ms = val * 60_000;
  if (unit.startsWith('s') || unit === '秒' || unit === '秒钟') {
    ms = val * 1_000;
  } else if (unit.startsWith('m') || unit === '分' || unit === '分钟') {
    ms = val * 60_000;
  } else if (unit.startsWith('h') || unit.includes('小时') || unit.includes('钟头')) {
    ms = val * 3_600_000;
  } else if (unit.startsWith('d') || unit === '天') {
    ms = val * 86_400_000;
  }

  return Math.max(ms, MIN_LOOP_INTERVAL_MS);
}

/**
 * 解析 /loop 命令的输入字符串为 (intervalMs, prompt)
 */
export function parseLoopCommandInput(rawInput: string): {
  intervalMs: number;
  prompt: string;
} {
  const args = rawInput.trim().replace(/^\/loop\s*/i, '').trim();
  if (!args) {
    return { intervalMs: DEFAULT_LOOP_INTERVAL_MS, prompt: '' };
  }

  // 1. 特殊前缀短语: e.g. "半小时 检查构建" 或 "每隔半小时 检查构建"
  const specialPrefixMatch = args.match(
    /^(?:every\s+|each\s+|每隔?\s*)?(半小时|半个小时|半个钟头|1个半小时|一个半小时|每天|每日)\s+(.+)$/i,
  );
  if (specialPrefixMatch) {
    const intervalStr = specialPrefixMatch[1];
    const prompt = specialPrefixMatch[2].trim();
    return { intervalMs: parseNaturalInterval(intervalStr), prompt };
  }

  // 2. 带有单位的前缀: e.g. "5m do something", "10分钟 检查PR", "every 2 hours do something", "每隔2小时 检查"
  const unitRegex =
    '(?:s|sec|secs|second|seconds|秒|秒钟|m|min|mins|minute|minutes|分|分钟|h|hr|hrs|hour|hours|个?小时|个?钟头|d|day|days|天)';
  const prefixMatch = args.match(
    new RegExp(`^(?:every\\s+|each\\s+|每隔?\\s*)?(\\d+\\s*${unitRegex})\\s+(.+)$`, 'i'),
  );
  if (prefixMatch) {
    const intervalStr = prefixMatch[1];
    const prompt = prefixMatch[2].trim();
    return { intervalMs: parseNaturalInterval(intervalStr), prompt };
  }

  // 3. 纯数字前缀 (默认按分钟处理): e.g. "10 检查构建"
  const prefixDigitMatch = args.match(/^(\d+)\s+(.+)$/);
  if (prefixDigitMatch) {
    const val = parseInt(prefixDigitMatch[1], 10);
    if (val >= 1 && val <= 1440) {
      return {
        intervalMs: Math.max(val * 60_000, MIN_LOOP_INTERVAL_MS),
        prompt: prefixDigitMatch[2].trim(),
      };
    }
  }

  // 4. 后缀 interval: e.g. "check something every 2 hours" 或 "检查构建 每隔10分钟"
  const suffixMatch = args.match(
    new RegExp(
      `\\s+(?:every|each|每隔?)\\s*(\\d+\\s*${unitRegex}|半小时|半个小时|半个钟头|1个半小时|一个半小时|每天|每日)\\s*$`,
      'i',
    ),
  );
  if (suffixMatch && suffixMatch.index !== undefined) {
    const intervalStr = suffixMatch[1];
    const prompt = args.slice(0, suffixMatch.index).trim();
    return { intervalMs: parseNaturalInterval(intervalStr), prompt };
  }

  // 5. 纯后缀单位: e.g. "check something 10m" 或 "检查构建 10分钟"
  const suffixPlainMatch = args.match(new RegExp(`\\s+(\\d+\\s*${unitRegex})\\s*$`, 'i'));
  if (suffixPlainMatch && suffixPlainMatch.index !== undefined) {
    const intervalStr = suffixPlainMatch[1];
    const prompt = args.slice(0, suffixPlainMatch.index).trim();
    return { intervalMs: parseNaturalInterval(intervalStr), prompt };
  }

  // 6. 默认回退: 整个文本作为 prompt
  return { intervalMs: DEFAULT_LOOP_INTERVAL_MS, prompt: args };
}

/**
 * 格式化毫秒数为人类可读字符串（用于 Toast 回显）
 */
export function formatIntervalReadable(ms: number): string {
  const seconds = Math.floor(ms / 1000);
  if (seconds < 60) {
    return `${seconds}s`;
  }
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) {
    return `${minutes}m`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingM = minutes % 60;
  if (hours < 24) {
    return remainingM ? `${hours}h${remainingM}m` : `${hours}h`;
  }
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

/**
 * 执行 /loop Slash 命令
 */
export async function executeLoopSlashCommand(inputValue: string): Promise<ActionResult> {
  const { default: useChatStore } = await import('@/store/useChatStore');
  const { createCronJob, triggerCronJob } = await import('@/services/cron');

  const { chatId, loading, selectedPersona } = useChatStore.getState();

  if (loading) {
    showI18nToast('commands.builtin.loopCreateFailed', undefined, { type: 'warning' });
    return { success: false, error: 'Cannot create loop task while streaming' };
  }

  const { intervalMs, prompt } = parseLoopCommandInput(inputValue);

  if (!prompt) {
    showI18nToast('commands.builtin.loopUsage', undefined, { type: 'info' });
    return { success: false, error: 'Missing loop prompt' };
  }

  const readableInterval = formatIntervalReadable(intervalMs);
  const jobName = prompt.length > 25 ? `${prompt.slice(0, 25)}...` : prompt;

  try {
    const job = await createCronJob({
      name: `Loop: ${jobName}`,
      job_type: 'agent',
      schedule: {
        kind: 'interval',
        interval_ms: intervalMs,
      },
      prompt,
      chat_id: chatId || undefined,
      agent_id: selectedPersona?.id ?? null,
      session_target: 'main',
      delete_after_run: false,
    });

    if (job?.id) {
      // 首跑即时触发策略 (Immediate First-run Policy)
      triggerCronJob(job.id).catch((err: unknown) => {
        console.warn('[LoopSlashCommand] First-run trigger failed:', err);
      });

      showI18nToast(
        'commands.builtin.loopCreated',
        { interval: readableInterval },
        { type: 'success' },
      );
      return { success: true, newInputValue: '' };
    }

    showI18nToast('commands.builtin.loopCreateFailed', undefined, { type: 'error' });
    return { success: false, error: 'Failed to create loop job' };
  } catch (error) {
    console.error('[LoopSlashCommand] Creation exception:', error);
    showI18nToast('commands.builtin.loopCreateFailed', undefined, { type: 'error' });
    return { success: false, error: 'Loop command exception' };
  }
}
