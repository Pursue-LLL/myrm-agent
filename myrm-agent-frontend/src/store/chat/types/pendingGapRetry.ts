/**
 * [OUTPUT]
 * PendingGapRetry: deferred entitlement-gap resend payload type.
 *
 * [POS]
 * Chat store contract type for capability/skill gap auto-retry lifecycle.
 */

import type { BuiltinToolId } from './builtinTools';

export type PendingGapRetry =
  | { kind: 'capability'; text: string; toolId: BuiltinToolId }
  | { kind: 'skill'; text: string; skillId: string };
