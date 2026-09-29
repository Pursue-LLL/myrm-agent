/**
 * [INPUT]
 * - 会话消息列表（仅取近期若干轮的 content 做词频统计）
 *
 * [OUTPUT]
 * - extractKeyterms: 供 STT 引擎做识别偏置的领域热词列表
 *
 * [POS]
 * STT 热词提取纯函数。桌面 composer 与移动端指挥条共用同一实现，
 * 保证同一会话在两端的口述识别词表一致，避免两端识别质量分叉。
 */

const KEYTERM_PATTERN =
  /(?:[A-Z][a-z]+(?:[A-Z][a-z]+)+|[A-Z]{2,}[a-z]*|[a-zA-Z][\w.-]{2,}(?:\.[\w]+)+|[一-鿿]{2,4}(?:[一-鿿]+)?)/g;

const MAX_KEYTERMS = 15;
const RECENT_MESSAGE_WINDOW = 6;

export function extractKeyterms(messages: { content: string; role: string }[]): string[] {
  const recent = messages.slice(-RECENT_MESSAGE_WINDOW);
  const text = recent.map((m) => m.content).join(' ');
  const matches = text.match(KEYTERM_PATTERN);
  if (!matches) {
    return [];
  }

  const counts = new Map<string, number>();
  for (const m of matches) {
    const lower = m.toLowerCase();
    counts.set(lower, (counts.get(lower) || 0) + 1);
  }

  return [...counts.entries()]
    .filter(([, c]) => c >= 1)
    .sort((a, b) => b[1] - a[1])
    .slice(0, MAX_KEYTERMS)
    .map(([term]) => term);
}
