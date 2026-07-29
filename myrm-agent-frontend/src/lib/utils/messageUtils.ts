/**
 * 消息处理工具函数
 *
 * [OUTPUT]
 * - stripDatetimeTag: 剥离时间戳标签
 * - stripUiActionPayload: 剥离 Agent 用 ui_action JSON 块
 * - stripUserMessageDisplayText: 用户消息展示用清理（含 explicit skill wire 前缀）
 * - parseExplicitSkillActivation: 解析 `[use s1,s2]` wire 前缀
 * - buildExplicitSkillWireMessage: 由 pending activation + 用户文本构建 wire
 * - formatSkillChipLabel: Skill chip 展示名
 * - stripMarkdown: 剥离 markdown 语法为纯文本
 * - getBrowserTimezone: 获取浏览器时区
 *
 * [POS]
 * 消息文本清理和格式化工具集。
 */

/**
 * 剥离消息中的时间戳标签（向后兼容旧数据中已持久化的标签）
 */
export const stripDatetimeTag = (text: string): string => {
  return text.replace(/<current_datetime>[\s\S]*?<\/current_datetime>/g, '').trim();
};

/** Strip machine-readable UI action payload appended for the Agent (not shown in chat UI). */
export const stripUiActionPayload = (text: string): string => {
  return text.replace(/\n?<ui_action_data>[\s\S]*?<\/ui_action_data>\s*$/g, '').trim();
};

/** Matches harness `_preload_explicit_skill()` and channel `skill_command_handler` wire prefix. */
const EXPLICIT_SKILL_ACTIVATION_PATTERN =
  /^\[use\s+([\w,\s-]+)\]\s*(?:\[instruction:\s*([^\]]*)\]\s*)?(.*)$/s;

export interface ExplicitSkillActivation {
  skillNames: string[];
  instruction: string | null;
  userText: string;
}

export const formatSkillChipLabel = (skillName: string): string =>
  skillName.replace(/_skill$/, '').replace(/_/g, ' ');

/** Parse `[use s1,s2] [instruction: ...] user text` wire prefix when present. */
export const parseExplicitSkillActivation = (text: string): ExplicitSkillActivation | null => {
  const match = text.match(EXPLICIT_SKILL_ACTIVATION_PATTERN);
  if (!match) {
    return null;
  }
  const skillNames = match[1]
    .split(',')
    .map((name) => name.trim())
    .filter(Boolean);
  if (skillNames.length === 0) {
    return null;
  }
  const instruction = match[2]?.trim() ? match[2].trim() : null;
  const userText = (match[3] ?? '').trim();
  return { skillNames, instruction, userText };
};

export const stripExplicitSkillActivationPrefix = (text: string): string => {
  const parsed = parseExplicitSkillActivation(text);
  if (!parsed) {
    return text;
  }
  return parsed.userText;
};

/** Build harness-visible wire message from pending activation + composer user text. */
export const buildExplicitSkillWireMessage = (
  activation: Pick<ExplicitSkillActivation, 'skillNames' | 'instruction'>,
  userText: string,
): string => {
  const names = activation.skillNames.join(',');
  const instructionPart = activation.instruction ? `[instruction: ${activation.instruction}] ` : '';
  const trimmedUser = userText.trim();
  if (!trimmedUser) {
    return `[use ${names}] ${instructionPart}`.trim();
  }
  return `[use ${names}] ${instructionPart}${trimmedUser}`.trim();
};

/** User-visible chat text: datetime tag + hidden ui_action + skill wire prefix removed. */
export const stripUserMessageDisplayText = (text: string): string => {
  return stripExplicitSkillActivationPrefix(stripUiActionPayload(stripDatetimeTag(text)));
};

/** 剥离 markdown 语法为纯文本，用于预览、TTS 等场景 */
export function stripMarkdown(text: string): string {
  return text
    .replace(
      /<(?:think|thinking|thought|antthinking|reasoning|REASONING_SCRATCHPAD)>[\s\S]*?<\/(?:think|thinking|thought|antthinking|reasoning|REASONING_SCRATCHPAD)>/gi,
      '',
    )
    .replace(/<citation[^>]*><\/citation>/g, '')
    .replace(/```[\s\S]*?```/g, '')
    .replace(/`[^`]+`/g, '')
    .replace(/!\[.*?\]\(.*?\)/g, '')
    .replace(/\[([^\]]+)\]\(.*?\)/g, '$1')
    .replace(/#{1,6}\s/g, '')
    .replace(/[*_~]{1,3}/g, '')
    .replace(/>\s/g, '')
    .replace(/[-*+]\s/g, '')
    .replace(/\d+\.\s/g, '')
    .replace(/\|.*\|/g, '')
    .replace(/[-:]+\|/g, '')
    .replace(/\n{2,}/g, '\n')
    .trim();
}

/**
 * 获取浏览器的 IANA 时区标识符（如 "Asia/Shanghai"）
 */
export const getBrowserTimezone = (): string => {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone;
  } catch {
    return 'UTC';
  }
};
