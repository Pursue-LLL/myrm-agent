/**
 * [INPUT]
 * @/services/agent::CommandBindingConfig (POS: 智能体命令绑定 DTO)
 *
 * [OUTPUT]
 * BindingIssue, sanitizeCommandToken, parseAliasList, normalizeBinding, findBindingIssues, toBindingsPayload,
 * areBindingsEqual: 命令绑定的输入清洗、逐条校验、提交载荷与脏检查
 *
 * [POS]
 * 命令绑定编辑的纯逻辑层。命令名与别名都要能以 `/名称` 触发，只保留字母、数字、下划线与连字符，长度不超过服务端上限；
 * 提交前每条绑定必须补全（有命令名且至少一个技能）且命令名与别名互不重名，空草稿以 null 清空服务端绑定。
 */

import type { CommandBindingConfig } from '@/services/agent';

export type BindingIssue = 'incomplete' | 'duplicate';

/** 与服务端 `CommandBindingConfig.command_name` 的 max_length 一致，超出会被 422 拒绝。 */
const COMMAND_TOKEN_MAX_LENGTH = 50;

const FORBIDDEN_TOKEN_CHARS = /[^a-zA-Z0-9_-]/g;

export function sanitizeCommandToken(raw: string): string {
  return raw.replace(FORBIDDEN_TOKEN_CHARS, '').slice(0, COMMAND_TOKEN_MAX_LENGTH);
}

export function parseAliasList(raw: string): string[] {
  return raw.split(',').map(sanitizeCommandToken).filter(Boolean);
}

/** 服务端会补全可选字段；统一补全后，持久化值与草稿才能做结构比较。 */
export function normalizeBinding(binding: CommandBindingConfig): Required<CommandBindingConfig> {
  return {
    command_name: binding.command_name,
    skill_ids: binding.skill_ids ?? [],
    description: binding.description ?? '',
    aliases: binding.aliases ?? [],
    instruction: binding.instruction ?? '',
  };
}

function bindingTokens(binding: CommandBindingConfig): Set<string> {
  const tokens = [binding.command_name, ...(binding.aliases ?? [])];
  return new Set(tokens.filter(Boolean).map((token) => token.toLowerCase()));
}

/** 与 `bindings` 按下标对齐；null 表示该条可提交。命令名与别名大小写不敏感地互不重名。 */
export function findBindingIssues(bindings: readonly CommandBindingConfig[]): (BindingIssue | null)[] {
  const tokenSets = bindings.map(bindingTokens);
  const tokenOwners = new Map<string, number>();
  for (const tokens of tokenSets) {
    for (const token of tokens) {
      tokenOwners.set(token, (tokenOwners.get(token) ?? 0) + 1);
    }
  }
  return bindings.map((binding, index) => {
    if (!binding.command_name || (binding.skill_ids ?? []).length === 0) {
      return 'incomplete';
    }
    for (const token of tokenSets[index]) {
      if ((tokenOwners.get(token) ?? 0) > 1) {
        return 'duplicate';
      }
    }
    return null;
  });
}

/** 空草稿返回 null：服务端以显式 null 清空绑定，省略该字段则保持不变。 */
export function toBindingsPayload(bindings: readonly CommandBindingConfig[]): CommandBindingConfig[] | null {
  return bindings.length > 0 ? bindings.map(normalizeBinding) : null;
}

export function areBindingsEqual(a: readonly CommandBindingConfig[], b: readonly CommandBindingConfig[]): boolean {
  return JSON.stringify(a.map(normalizeBinding)) === JSON.stringify(b.map(normalizeBinding));
}
