/**
 * [INPUT]
 * - `./types` ConfigChange / SyncResult (POS: queued write, backend answer)
 *
 * [OUTPUT]
 * partitionByAnswer: sorts the changes of a batch by what the answer says about their key.
 * mergeAnswers: the answers to the keys of one batch, sent one by one, as the single answer the batch would have received.
 *
 * [POS]
 * How a backend answer maps onto the batch it answers. Pure: the outbox decides what to do with each part.
 */
import type { ConfigChange, SyncResult } from './types';

export interface AnswerPartition {
  /** The backend took them. */
  accepted: ConfigChange[];
  /** The answer names a version clash on their key. */
  rejected: ConfigChange[];
  /** The answer neither takes nor rejects them: their fate is unknown, so they stay queued. */
  unnamed: ConfigChange[];
}

export function partitionByAnswer(batch: ConfigChange[], answer: SyncResult): AnswerPartition {
  const clashed = new Set(answer.conflicts);
  const partition: AnswerPartition = { accepted: [], rejected: [], unnamed: [] };
  for (const change of batch) {
    if (clashed.has(change.key)) {
      partition.rejected.push(change);
    } else if (answer.success || answer.newVersions.has(change.key)) {
      partition.accepted.push(change);
    } else {
      partition.unnamed.push(change);
    }
  }
  return partition;
}

/** Without answers it is the answer to nothing sent: a success naming no key. */
export function mergeAnswers(answers: SyncResult[]): SyncResult {
  const merged: SyncResult = { success: true, conflicts: [], newVersions: new Map() };
  for (const answer of answers) {
    merged.success &&= answer.success;
    merged.conflicts.push(...answer.conflicts);
    for (const [key, version] of answer.newVersions) {
      merged.newVersions.set(key, version);
    }
    merged.error ??= answer.error;
  }
  return merged;
}
