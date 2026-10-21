/**
 * [INPUT]
 * - CompactionEntry, CompactedMessageSnapshot from ./compactionTypes
 * - ArchivedChatMessage from '@/services/chat'
 * - LastCompactionMeta from '@/store/chat/types'
 *
 * [OUTPUT]
 * - parseCompactionEntry: Converts unstructured summary markdown & metadata into structured CompactionEntry
 *
 * [POS]
 * Pure parser utility converting chat compaction data to Item 27 milestone card entry.
 * Single file < 120 lines. Zero `any` types.
 */

import type { CompactionEntry, CompactedMessageSnapshot } from './compactionTypes';
import type { ArchivedChatMessage } from '@/services/chat';
import type { LastCompactionMeta } from '@/store/chat/types';

function extractSectionContent(text: string, headerKeywords: string[]): string {
  for (const keyword of headerKeywords) {
    const regex = new RegExp(`(?:###?\\s*[*_]*${keyword}[*_]*|[*_]*${keyword}:[*_]*)\\s*([^#\\n][\\s\\S]*?)(?=(?:\\n###?\\s|\\n[*_]*[A-Za-z\\u4e00-\\u9fa5]+:[*_]*|$))`, 'i');
    const match = regex.exec(text);
    if (match?.[1]?.trim()) {
      return match[1].trim();
    }
  }
  return '';
}

function extractListItems(text: string, headerKeywords: string[]): string[] {
  const section = extractSectionContent(text, headerKeywords);
  if (!section) {
    return [];
  }
  return section
    .split('\n')
    .map((line) => line.replace(/^[\s*-+]+(?:\d+\.)?\s*/, '').trim())
    .filter((line) => line.length > 0);
}

export function parseCompactionEntry(
  summaryText: string,
  lastCompactionMeta?: LastCompactionMeta | null,
  archiveMessages?: ArchivedChatMessage[],
): CompactionEntry {
  const cleaned = summaryText.trim();
  const goal = extractSectionContent(cleaned, ['目标', 'Goal', '任务目标']) || cleaned.slice(0, 120) || '上下文压缩与记忆提炼';
  const progress = extractSectionContent(cleaned, ['进展', 'Progress', '完成情况']) || '已提炼当前会话关键上下文并存入只读归档。';
  const keyDecisions = extractListItems(cleaned, ['决策', 'Key Decisions', '核心决策', 'Decisions']);
  const nextSteps = extractListItems(cleaned, ['下一步', 'Next Steps', '后续动作', 'Plans']);
  const criticalContext = extractSectionContent(cleaned, ['关键上下文', 'Critical Context', 'Context', '重要背景']);

  const filesTouched = lastCompactionMeta?.exactAnchors?.filePaths ?? [];

  const originalMessages: CompactedMessageSnapshot[] = (archiveMessages ?? []).map((msg) => ({
    id: msg.id,
    role: msg.role === 'user' ? 'user' : 'assistant',
    content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content),
    timestamp: msg.created_at ?? undefined,
  }));

  return {
    id: lastCompactionMeta?.snapshotPath || `compaction-${Date.now()}`,
    compactedAt: new Date().toISOString(),
    compactedMessagesCount: originalMessages.length,
    savedTokens: lastCompactionMeta?.tokensSaved ?? 0,
    goal,
    progress,
    keyDecisions: keyDecisions.length > 0 ? keyDecisions : ['已提炼核心推理链路与业务状态'],
    nextSteps: nextSteps.length > 0 ? nextSteps : ['继续推进当前任务上下文'],
    criticalContext,
    filesTouched,
    originalMessages,
  };
}
