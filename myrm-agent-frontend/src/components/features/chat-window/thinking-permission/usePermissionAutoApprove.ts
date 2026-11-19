'use client';

/**
 * [INPUT]
 * - usePermissionTierStore::usePermissionTierStore (POS: Reactive permission state.)
 * - thinkingPermissionTypes::PermissionCheckResult (POS: Check result contract.)
 *
 * [OUTPUT]
 * - usePermissionAutoApprove: Hook that evaluates tool approval requests against current tier
 *   and triggers safe autonomous approval or high-risk warnings. A call held for the user is never approved here.
 *
 * [POS]
 * Bridges the 3-Tier permission mode directly into tool approval dialogs and cards,
 * automatically approving safe file edits while forcefully flagging high-risk commands.
 * No tier approves a call the harness holds for the user alone (`held`): that answer is the user's.
 */

import { useEffect, useMemo, useRef } from 'react';
import { usePermissionTierStore } from './usePermissionTierStore';
import type { PermissionCheckResult } from './thinkingPermissionTypes';

export interface UsePermissionAutoApproveOptions {
  toolName: string;
  toolInput: Record<string, unknown>;
  onApprove: () => Promise<void> | void;
  enabled?: boolean;
  /** The call is the user's alone to answer (`ToolApprovalRequest.heldForPerson`); no tier approves it. */
  held?: boolean;
  autoApproveDelayMs?: number;
}

export interface UsePermissionAutoApproveResult {
  tier: string;
  checkResult: PermissionCheckResult;
  isHighRiskIntercepted: boolean;
  isAutoApproved: boolean;
}

export function usePermissionAutoApprove({
  toolName,
  toolInput,
  onApprove,
  enabled = true,
  held = false,
  autoApproveDelayMs = 400,
}: UsePermissionAutoApproveOptions): UsePermissionAutoApproveResult {
  const tier = usePermissionTierStore((state) => state.tier);
  const checkPermission = usePermissionTierStore((state) => state.checkPermission);
  const hasTriggeredRef = useRef(false);

  const checkResult = useMemo(() => {
    return checkPermission(toolName, toolInput as { command?: string; path?: string });
  }, [checkPermission, toolName, toolInput]);

  const isHighRiskIntercepted = checkResult.reason === 'semi_auto_high_risk_intercepted';
  // Folded into the result, not only the effect: the card shows "approving automatically" and disables its approve
  // button while this is true, so a held call must not read as auto-approved at all.
  const isAutoApproved = !held && checkResult.approved && tier !== 'strict';

  useEffect(() => {
    if (!enabled || !isAutoApproved || hasTriggeredRef.current) {
      return;
    }

    hasTriggeredRef.current = true;
    const timer = setTimeout(() => {
      void onApprove();
    }, autoApproveDelayMs);

    return () => {
      clearTimeout(timer);
    };
  }, [enabled, isAutoApproved, onApprove, autoApproveDelayMs]);

  return {
    tier,
    checkResult,
    isHighRiskIntercepted,
    isAutoApproved,
  };
}
