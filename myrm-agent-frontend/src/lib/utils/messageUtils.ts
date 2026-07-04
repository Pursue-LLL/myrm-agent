/**
 * 消息处理工具函数
 *
 * [OUTPUT]
 * - stripDatetimeTag: 剥离时间戳标签
 * - stripUiActionPayload: 剥离 Agent 用 ui_action JSON 块
 * - stripUserMessageDisplayText: 用户消息展示用清理
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

/** User-visible chat text: datetime tag + hidden ui_action payload removed. */
export const stripUserMessageDisplayText = (text: string): string => {
  return stripUiActionPayload(stripDatetimeTag(text));
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
