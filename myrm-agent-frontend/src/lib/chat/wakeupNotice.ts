/**
 * [INPUT]
 * - @/store/chat/types::WakeupNoticeKind (POS: what the server did with a settled background task)
 *
 * [OUTPUT]
 * - WAKEUP_NOTICE_METADATA_KEY: the key the server sets on the row's metadata (its `WAKEUP_NOTICE_KEY`).
 * - parseWakeupNoticeKind: the kind a metadata value names, or undefined for any other value.
 * - isInertWakeupNotice: whether the note belongs to a settlement that started no turn.
 *
 * [POS]
 * One reading of the wake notices the server appends as user-role rows. They are the system's notes about finished
 * background work, never something the user said: a note that woke the agent is hidden behind the reply it caused,
 * a note that did not is a quiet line, and an inert note is not a turn of the conversation.
 */

import type { WakeupNoticeKind } from '@/store/chat/types';

export const WAKEUP_NOTICE_METADATA_KEY = 'wakeup_notice';

const WAKEUP_NOTICE_KINDS: readonly WakeupNoticeKind[] = ['followup', 'degraded', 'suppressed'];

export function parseWakeupNoticeKind(value: unknown): WakeupNoticeKind | undefined {
  return WAKEUP_NOTICE_KINDS.find((kind) => kind === value);
}

/** A degraded or suppressed settlement starts no turn, so nothing answers its note. */
export function isInertWakeupNotice(kind: WakeupNoticeKind | undefined): boolean {
  return kind === 'degraded' || kind === 'suppressed';
}
