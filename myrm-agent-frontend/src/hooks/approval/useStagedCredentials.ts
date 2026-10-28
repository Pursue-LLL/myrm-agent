'use client';

/**
 * [INPUT]
 * - @/lib/approval/oneTimeCredentials::stageOneTimeCredentials, wipeOneTimeCredentials (POS: 一次性凭据 HTTP 客户端)
 *
 * [OUTPUT]
 * - useStagedCredentials: 一张审批卡上已暂存凭据的状态机（暂存 / 撤回 / 丢弃 / 到期自动销毁）
 *
 * [POS]
 * 凭据状态属于审批卡而不是录入表单：卡片切到编辑、拒绝视图时表单会卸载，已暂存的凭据与到期计时必须留在这里。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import {
  stageOneTimeCredentials,
  wipeOneTimeCredentials,
  type CredentialToStage,
  type StagedCredential,
} from '@/lib/approval/oneTimeCredentials';

export interface StagedCredentials {
  items: StagedCredential[];
  /** Client-clock deadline: the shortest lifetime among the staged credentials. */
  expiresAtMs: number;
}

interface UseStagedCredentialsParams {
  chatId: string;
  /** The command text exactly as the approval card shows it. */
  command: string;
  onExpired: () => void;
}

export function useStagedCredentials({ chatId, command, onExpired }: UseStagedCredentialsParams) {
  const [staged, setStaged] = useState<StagedCredentials | null>(null);
  const onExpiredRef = useRef(onExpired);
  useEffect(() => {
    onExpiredRef.current = onExpired;
  });

  const stage = useCallback(
    async (credentials: CredentialToStage[]) => {
      const items = await stageOneTimeCredentials(chatId, command, credentials);
      const shortestTtl = Math.min(...credentials.map((credential) => credential.ttlSeconds));
      setStaged({ items, expiresAtMs: Date.now() + shortestTtl * 1000 });
    },
    [chatId, command],
  );

  /** Take the credentials back; throws when the server could not destroy them, so the caller can say so. */
  const revoke = useCallback(async () => {
    if (staged) {
      await wipeOneTimeCredentials(
        chatId,
        staged.items.map((item) => item.handleId),
      );
      setStaged(null);
    }
  }, [chatId, staged]);

  /** Drop the credentials without waiting for the server (the card is leaving, or the command changed). */
  const discard = useCallback(() => {
    if (staged) {
      wipeOneTimeCredentials(
        chatId,
        staged.items.map((item) => item.handleId),
      ).catch(() => undefined);
      setStaged(null);
    }
  }, [chatId, staged]);

  useEffect(() => {
    if (!staged) {
      return;
    }
    const timer = setTimeout(
      () => {
        discard();
        onExpiredRef.current();
      },
      Math.max(0, staged.expiresAtMs - Date.now()),
    );
    return () => clearTimeout(timer);
  }, [discard, staged]);

  return useMemo(() => ({ staged, stage, revoke, discard }), [staged, stage, revoke, discard]);
}
