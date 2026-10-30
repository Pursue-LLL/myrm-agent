/**
 * [INPUT] POST /api/v1/evolution/fix (force_retry) 与调用方提供的本地化提示文案
 * [OUTPUT] useEvolutionForceRetry: 审计行「强制重试」的进行中状态与提交动作
 * [POS] features/skills 进化审计面板的重试逻辑；技能被防自动修改保护锁定时服务端返回 409，给出解锁指引而非泛化失败
 */
'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import type { SkillGrowthAuditEntry } from '@/services/skill/growth';

const SKILL_LOCKED_STATUS = 409;

interface ForceRetryMessages {
  started: string;
  failed: string;
  /** Shown when the skill is locked against automatic changes; tells the user where to unlock it. */
  locked: string;
}

interface UseEvolutionForceRetryParams {
  messages: ForceRetryMessages;
  /** Called once the server accepted the retry, so the row can move on. */
  onStarted: (eventId: string) => void;
}

export function useEvolutionForceRetry({ messages, onStarted }: UseEvolutionForceRetryParams) {
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const retry = async (entry: SkillGrowthAuditEntry): Promise<void> => {
    setRetryingIds((prev) => new Set(prev).add(entry.eventId));
    try {
      const res = await fetch(`/api/v1/evolution/fix/${entry.skillId || entry.skillName}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: entry.reason, force_retry: true }),
      });
      if (res.status === SKILL_LOCKED_STATUS) {
        toast.error(messages.locked);
        return;
      }
      if (!res.ok) {
        throw new Error('Failed to force retry');
      }
      toast.success(messages.started);
      onStarted(entry.eventId);
    } catch {
      toast.error(messages.failed);
    } finally {
      setRetryingIds((prev) => {
        const next = new Set(prev);
        next.delete(entry.eventId);
        return next;
      });
    }
  };

  return { retryingIds, retry };
}
