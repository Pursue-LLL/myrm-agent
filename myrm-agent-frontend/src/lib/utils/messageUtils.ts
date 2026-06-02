/**
 * 消息处理工具函数
 *
 * [OUTPUT]
 * - stripDatetimeTag: 剥离时间戳标签
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
