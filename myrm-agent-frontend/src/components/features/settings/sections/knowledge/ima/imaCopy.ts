/**
 * [INPUT]
 * @/lib/api::ApiError (POS: carries the server's `{code, message}` as `businessCode`)
 * @/services/wiki/ima::ImaStatus, ImaItemCounts (POS: ima status DTOs)
 *
 * [OUTPUT]
 * ImaView / ImaSyncMode: which screen the card shows and what the running sync is doing
 * deriveImaView / deriveImaSyncMode / imaProgress / imaSkippedCount / imaAttentionCount: state derivation from `ImaStatus`
 * imaErrorKey / imaReasonKey / imaNoteKeys / imaKindKey / formatImaChars: server code → `settings.wiki.ima.*` i18n key
 *
 * [POS]
 * The only place that knows ima's status and reason codes. The server never sends wording, so every code the UI can meet
 * resolves here to a locale key, and an unknown code falls back to a generic line instead of leaking the raw code.
 */

import { ApiError } from '@/lib/api';
import type { ImaItemCounts, ImaStatus } from '@/services/wiki/ima';

export type ImaView = 'connect' | 'reconnect' | 'choose' | 'sync';

export type ImaSyncMode = 'reading' | 'importing' | 'waiting' | 'paused' | 'upToDate';

const ERROR_CODES = new Set([
  'ima_auth_failed',
  'ima_rate_limited',
  'ima_unreachable',
  'ima_not_connected',
  'ima_no_selection',
  'ima_sync_not_started',
  'ima_credentials_missing',
  'dedup_review_required',
  'sync_unavailable',
]);

const REASON_CODES = new Set([
  'unsupported_type',
  'no_download_url',
  'no_text',
  'too_large',
  'security',
  'notes_permission',
  'timeout',
  'transient',
  'permanent',
  'page_unavailable',
  'auth',
  'rate_limit',
]);

const NOTE_CODES = new Set(['plain_text', 'images_remote', 'body_truncated', 'layout_flattened', 'redacted']);

const KIND_CODES = new Set([
  'pdf',
  'web',
  'word',
  'ppt',
  'excel',
  'wechat',
  'markdown',
  'image',
  'note',
  'ai_session',
  'text',
  'xmind',
  'audio',
  'video',
  'html',
  'epub',
]);

export function deriveImaView(status: ImaStatus, editingSelection: boolean): ImaView {
  if (!status.connected) {
    return 'connect';
  }
  if (status.needs_reauth) {
    return 'reconnect';
  }
  return editingSelection || status.job.state === 'none' ? 'choose' : 'sync';
}

export function deriveImaSyncMode(status: ImaStatus): ImaSyncMode {
  if (status.job.state === 'paused') {
    return 'paused';
  }
  if (status.phase === 'inventory') {
    return 'reading';
  }
  if (status.phase === 'fetch') {
    return 'importing';
  }
  return status.backfill_complete ? 'upToDate' : 'waiting';
}

/** The first import is still filling the wiki; later passes only top it up, so only then does a bar make sense. */
export function isImaBackfilling(status: ImaStatus): boolean {
  return status.job.state === 'active' && !status.backfill_complete;
}

export function imaProgress(counts: ImaItemCounts): { done: number; total: number; percent: number } {
  const done = Math.max(0, counts.total - counts.pending);
  return { done, total: counts.total, percent: counts.total > 0 ? Math.round((done / counts.total) * 100) : 0 };
}

/** Items ima has that were deliberately not imported (unsupported type, too big, held by the safety check). */
export function imaSkippedCount(counts: ImaItemCounts): number {
  return counts.unsupported + counts.too_large + counts.blocked;
}

export function imaAttentionCount(counts: ImaItemCounts): number {
  return counts.failed + imaSkippedCount(counts);
}

/** Keeps polling only while something can still change on its own. */
export function shouldPollIma(status: ImaStatus | null): boolean {
  return (
    status !== null &&
    status.connected &&
    status.job.state === 'active' &&
    (status.phase !== 'idle' || !status.backfill_complete)
  );
}

export function imaErrorKey(error: unknown): string {
  const code = error instanceof ApiError ? error.businessCode : undefined;
  return code && ERROR_CODES.has(code) ? `errors.${code}` : 'errors.generic';
}

export function imaReasonKey(reason: string): string {
  return REASON_CODES.has(reason) ? `reasons.${reason}` : 'reasons.generic';
}

export function imaNoteKeys(notes: readonly string[]): string[] {
  return notes.filter((note) => NOTE_CODES.has(note)).map((note) => `notes.${note}`);
}

export function imaKindKey(kind: string): string {
  return KIND_CODES.has(kind) ? `kinds.${kind}` : 'kinds.other';
}

export function formatImaChars(chars: number, locale: string): string {
  return new Intl.NumberFormat(locale, { notation: 'compact', maximumFractionDigits: 1 }).format(chars);
}
