/**
 * [INPUT]
 * - Raw speech transcript (interim or final text from STT)
 *
 * [OUTPUT]
 * - VoiceRouteDecision: { tier: 'tier0_local_bypass' | 'tier1_agent_llm', action?: VoiceCommandAction, normalizedText: string }
 *
 * [POS]
 * Client-side tier-0 local bypass matcher. Directly routes deterministic control/navigation
 * commands without waiting for or paying LLM tokens, falling back to tier-1 agent LLM
 * for complex semantic tasks.
 */

export type VoiceCommandAction =
  | 'stop_execution'
  | 'pause_execution'
  | 'resume_execution'
  | 'retry_execution'
  | 'new_session'
  | 'clear_history'
  | 'open_taskboard'
  | 'open_settings'
  | 'toggle_sidebar'
  | 'export_session';

export type VoiceRouteTier = 'tier0_local_bypass' | 'tier1_agent_llm';

export interface VoiceRouteDecision {
  readonly tier: VoiceRouteTier;
  readonly action?: VoiceCommandAction;
  readonly rawText: string;
  readonly normalizedText: string;
  readonly matchedKeyword?: string;
}

const COLLOQUIAL_PREFIX_RE =
  /^(?:请(?:帮我|给我)?|麻烦你?(?:帮我)?|帮我|给我|赶紧|立刻|马上|请先|先帮我|先给我|现在|务必)\s*/u;
const TRAILING_PUNCTUATION_RE = /[.!?。！？，、~\s]+$/u;

const CONTROL_PATTERNS: ReadonlyArray<{ readonly action: VoiceCommandAction; readonly patterns: ReadonlyArray<string> }> = [
  { action: 'stop_execution', patterns: ['stop', 'cancel', 'halt', 'abort', '停止', '取消', '别跑了', '中断', '别动了'] },
  { action: 'pause_execution', patterns: ['pause', 'hold on', '暂停', '先停一下', '稍等'] },
  { action: 'resume_execution', patterns: ['resume', 'continue', 'go on', '继续', '恢复', '接着跑'] },
  { action: 'retry_execution', patterns: ['retry', 'rerun', 'try again', '重试', '重新跑', '再试一次'] },
  { action: 'new_session', patterns: ['new chat', 'new session', 'new conversation', '新建会话', '开个新对话', '重新开一个'] },
  { action: 'clear_history', patterns: ['clear history', 'clear messages', 'reset chat', '清空历史', '清空对话', '抹掉记录'] },
  { action: 'open_taskboard', patterns: ['open tasks', 'show taskboard', 'open kanban', '打开任务板', '查看任务', '打开看板'] },
  { action: 'open_settings', patterns: ['open settings', 'show preferences', '打开设置', '偏好设置', '系统设置'] },
  { action: 'toggle_sidebar', patterns: ['toggle sidebar', 'hide sidebar', 'show sidebar', '收起侧边栏', '展开侧边栏', '切换侧边栏'] },
  { action: 'export_session', patterns: ['export chat', 'export session', 'save transcript', '导出记录', '导出对话', '导出聊天'] },
];

export function normalizeVoiceInput(rawText: string): string {
  let cleaned = rawText.trim().toLowerCase().replace(TRAILING_PUNCTUATION_RE, '');
  let prev = '';
  while (cleaned !== prev) {
    prev = cleaned;
    cleaned = cleaned.replace(COLLOQUIAL_PREFIX_RE, '').trim();
  }
  return cleaned;
}

export function matchVoiceCommandBypass(rawText: string): VoiceRouteDecision {
  const normalized = normalizeVoiceInput(rawText);
  if (!normalized) {
    return {
      tier: 'tier1_agent_llm',
      rawText,
      normalizedText: normalized,
    };
  }

  for (const { action, patterns } of CONTROL_PATTERNS) {
    for (const pattern of patterns) {
      if (normalized === pattern) {
        return {
          tier: 'tier0_local_bypass',
          action,
          rawText,
          normalizedText: normalized,
          matchedKeyword: pattern,
        };
      }
    }
  }

  return {
    tier: 'tier1_agent_llm',
    rawText,
    normalizedText: normalized,
  };
}
