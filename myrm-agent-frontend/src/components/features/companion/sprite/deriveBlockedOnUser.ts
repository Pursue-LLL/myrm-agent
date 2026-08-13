/**
 * deriveBlockedOnUser — aggregates existing HITL store signals into one blocked flag.
 *
 * [INPUT]
 * - BlockedOnUserInput: queue lengths + messages + desktop/browser approval flags
 *
 * [OUTPUT]
 * - deriveBlockedOnUser(): true when any user action is required before the agent continues
 *
 * [POS]
 * Pure function used by PetOverlay to drive PetState.WAITING from store SSOT
 * (not from fragile pet-status-event dispatches).
 */

import { findActivePendingClarification } from '@/store/chat/clarificationState';

import type { Message } from '@/store/chat/types';

export interface BlockedOnUserInput {
  toolApprovalQueueLength: number;
  approvalQueueLength: number;
  hasPendingClarification: boolean;
  desktopControlPending: boolean;
  browserTakeoverPending: boolean;
}

/** Accepts messages for testability; production callers may pass a precomputed flag. */
export function deriveBlockedOnUser(input: BlockedOnUserInput): boolean {
  if (input.toolApprovalQueueLength > 0) {return true;}
  if (input.approvalQueueLength > 0) {return true;}
  if (input.desktopControlPending) {return true;}
  if (input.browserTakeoverPending) {return true;}
  return input.hasPendingClarification;
}

export function hasPendingClarificationFromMessages(messages: Message[]): boolean {
  return findActivePendingClarification(messages) !== null;
}
