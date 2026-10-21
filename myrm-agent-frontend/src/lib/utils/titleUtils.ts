/**
 * 会话标题管理与去重消歧工具函数
 *
 * 当自动生成或用户设定的会话标题与当前侧边栏列表中已有其他会话重名时，
 * 智能消歧并追加自增序号 (2), (3) 等，保持视觉唯一性且杜绝多层括号嵌套。
 */

/**
 * 解析标题的基准名与现有数字编号
 *
 * 例如:
 * - "方案讨论" -> { base: "方案讨论", index: 1 }
 * - "方案讨论 (2)" -> { base: "方案讨论", index: 2 }
 * - "方案讨论 (10)" -> { base: "方案讨论", index: 10 }
 */
export function parseTitleIndex(title: string): { base: string; index: number } {
  const trimmed = title.trim();
  if (!trimmed) {
    return { base: '', index: 1 };
  }

  const match = trimmed.match(/^(.*?)(?:\s+\((\d+)\))$/);
  if (match) {
    const base = match[1].trim();
    const index = parseInt(match[2], 10);
    if (!isNaN(index) && index > 0) {
      return { base, index };
    }
  }

  return { base: trimmed, index: 1 };
}

/**
 * 根据已有会话标题列表，为新标题生成不冲突的唯一标题
 *
 * @param candidateTitle 待检查的候选标题
 * @param existingTitles 现有会话列表中的所有标题（不含当前会话自身的原标题）
 * @returns 经过消歧处理的唯一标题
 */
export function disambiguateChatTitle(candidateTitle: string, existingTitles: string[]): string {
  const trimmedCandidate = candidateTitle.trim();
  if (!trimmedCandidate) {
    return 'Untitled Chat';
  }

  const existingSet = new Set(existingTitles.map((t) => t.trim()));
  if (!existingSet.has(trimmedCandidate)) {
    return trimmedCandidate;
  }

  const { base } = parseTitleIndex(trimmedCandidate);

  // 寻找已被占用的序号
  const usedIndices = new Set<number>();
  for (const title of existingSet) {
    const parsed = parseTitleIndex(title);
    if (parsed.base.toLowerCase() === base.toLowerCase()) {
      usedIndices.add(parsed.index);
    }
  }

  // 从 2 开始寻找最小未占用的序号
  let nextIndex = 2;
  while (usedIndices.has(nextIndex)) {
    nextIndex++;
  }

  return `${base} (${nextIndex})`;
}
