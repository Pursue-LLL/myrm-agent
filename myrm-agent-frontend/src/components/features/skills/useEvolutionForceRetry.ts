/**
 * [INPUT] POST /api/v1/evolution/fix (force_retry) 与调用方提供的本地化提示文案
 * [OUTPUT] useEvolutionForceRetry: 审计行「强制重试」的进行中状态与提交动作；canForceRetry: 审计行是否还有可重试的技能
 * [POS] features/skills 进化审计面板的重试逻辑；技能被防自动修改保护锁定时服务端返回 409，给出解锁指引而非泛化失败
 */
'use client';

import { useState } from 'react';
import { toast } from 'sonner';
import type { SkillGrowthAuditEntry } from '@/services/skill/growth';

const SKILL_LOCKED_STATUS = 409;
/** The unlock hint is a full sentence, which the default toast time is too short to read. */
const LOCKED_HINT_DURATION_MS = 8000;

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

/**
 * Whether a refused row names a skill the retry can act on. A new-skill draft the user rejected never became a
 * skill, so there is nothing to fix; a locked one does exist and is answered with the unlock hint.
 */
export function canForceRetry(entry: SkillGrowthAuditEntry): boolean {
  if (entry.status === 'BLOCKED_LOCKED') {
    return true;
  }
  if (entry.status !== 'REJECTED') {
    return false;
  }
  return !(entry.source === 'draft' && entry.growthType === 'skill_draft' && !entry.skillId);
}

export function useEvolutionForceRetry({ messages, onStarted }: UseEvolutionForceRetryParams) {
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const retry = async (entry: SkillGrowthAuditEntry): Promise<void> => {
    setRetryingIds((prev) => new Set(prev).add(entry.eventId));
    try {
      // The skill may be named by a directory name, which can hold characters a URL would read as its own syntax.
      const res = await fetch(`/api/v1/evolution/fix/${encodeURIComponent(entry.skillId || entry.skillName)}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason: entry.reason, force_retry: true }),
      });
      if (res.status === SKILL_LOCKED_STATUS) {
        toast.error(messages.locked, { duration: LOCKED_HINT_DURATION_MS });
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
