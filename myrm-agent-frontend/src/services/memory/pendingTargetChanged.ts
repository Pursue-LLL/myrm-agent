/**
 * [INPUT]
 * @/lib/api::ApiError (POS: backend error carrying the HTTP status in `code`)
 *
 * [OUTPUT]
 * isPendingTargetChanged: whether an approve failure means the memory a suggestion refers to changed after it was queued
 *
 * [POS]
 * The server answers 409 for that case and keeps the suggestion pending, so callers show a localized
 * "out of date" message instead of the raw backend text.
 */
import { ApiError } from '@/lib/api';

const HTTP_CONFLICT = 409;

export function isPendingTargetChanged(error: unknown): boolean {
  return error instanceof ApiError && error.code === HTTP_CONFLICT;
}
