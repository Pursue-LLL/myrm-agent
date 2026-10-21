/**
 * [INPUT]
 * - @/components/features/chat-window/cli-passthrough/cliPassthroughTypes
 *
 * [OUTPUT]
 * - parseCliPassThroughInput, auditCliCommand, formatCliOutputForContext
 *
 * [POS]
 * Pure computation engine for Item 194 (P0): DirectCliPassThroughWithContextVisibilitySwitchSuite.
 * Parses '!' vs '!!' prefixes, audits security barriers, and formats context injection blocks.
 */

import type {
  CliPassThroughMode,
  CliGuardAuditResult,
} from './cliPassthroughTypes';

export interface ParsedCliInput {
  readonly isCliCommand: boolean;
  readonly mode?: CliPassThroughMode;
  readonly command?: string;
}

const HIGH_RISK_PATTERNS: ReadonlyArray<{ readonly pattern: RegExp; readonly reason: string }> = [
  {
    pattern: /\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f?[a-zA-Z]*\s+|-rf\s+)*(\/|~|\$HOME|\.\.)(\s|$)/,
    reason: '高危操作拦截：禁止递归强制删除根目录或主工作区！',
  },
  {
    pattern: /\bmkfs(\.[a-zA-Z0-9]+)?\s+/,
    reason: '高危操作拦截：禁止直接格式化文件系统驱动器！',
  },
  {
    pattern: /:\s*(\(\s*\))?\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:/,
    reason: '恶意攻击拦截：禁止执行 Fork 炸弹！',
  },
  {
    pattern: /\bdd\s+if=.*of=(\/dev\/sd|\/dev\/nvme|\/dev\/disk)/,
    reason: '高危操作拦截：禁止对物理块设备写入裸数据！',
  },
  {
    pattern: /\bchmod\s+(-R\s+)?777\s+\/(\s|$)/,
    reason: '安全策略拦截：禁止破坏性放开根目录全局写权限！',
  },
];

export function parseCliPassThroughInput(input: string): ParsedCliInput {
  const trimmed = input.trim();
  if (!trimmed) {
    return { isCliCommand: false };
  }

  // 检查 '!!' 前缀（用户自省模式，0 Token，绝不进上下文）
  if (trimmed.startsWith('!!')) {
    const command = trimmed.slice(2).trim();
    if (!command) {
      return { isCliCommand: false };
    }
    return {
      isCliCommand: true,
      mode: 'user_inspection_only',
      command,
    };
  }

  // 检查 '!' 前缀（上下文注入模式，AI 可见）
  if (trimmed.startsWith('!')) {
    const command = trimmed.slice(1).trim();
    if (!command) {
      return { isCliCommand: false };
    }
    return {
      isCliCommand: true,
      mode: 'visible_to_context',
      command,
    };
  }

  return { isCliCommand: false };
}

export function auditCliCommand(command: string): CliGuardAuditResult {
  const normalized = command.trim();
  if (!normalized) {
    return { allowed: false, reason: '命令内容不能为空' };
  }

  for (const rule of HIGH_RISK_PATTERNS) {
    if (rule.pattern.test(normalized)) {
      return {
        allowed: false,
        reason: rule.reason,
      };
    }
  }

  return { allowed: true };
}

export function formatCliOutputForContext(
  command: string,
  output: string,
  exitCode: number,
): string {
  const statusLine = exitCode === 0 ? 'STATUS: SUCCESS' : `STATUS: FAILED (Exit Code: ${exitCode})`;
  return `[USER_CMD_EXEC]\n$ ${command}\n${statusLine}\n---\n${output.trim()}\n[/USER_CMD_EXEC]`;
}
