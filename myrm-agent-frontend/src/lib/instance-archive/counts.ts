/**
 * [INPUT]
 * - @/services/instanceArchive: ImportReport (type only)
 *
 * [OUTPUT]
 * - COUNT_KEYS, CountKey: the content counts a backup review and a restore result render
 * - losesHistory: whether restoring would leave fewer chats or messages than the app has now
 *
 * [POS]
 * One list of count keys shared by the review and the post-restore dialog. It must equal what
 * the backend report emits; the server architecture test pins the two together.
 */

import type { ImportReport } from '@/services/instanceArchive';

export const COUNT_KEYS = ['chats', 'messages', 'agents', 'skills', 'wiki_pages', 'cron_jobs'] as const;

export type CountKey = (typeof COUNT_KEYS)[number];

const HISTORY_KEYS = ['chats', 'messages'] as const;

export function losesHistory(report: Pick<ImportReport, 'counts' | 'current_counts'>): boolean {
  return HISTORY_KEYS.some((key) => (report.current_counts[key] ?? 0) > (report.counts[key] ?? 0));
}
