/**
 * [INPUT]
 * - @/components/features/sidebar/attention-hub/attentionHubTypes
 *
 * [OUTPUT]
 * - computePriorityWeight, sortAttentionItems, getCategoryMeta,
 *   formatRemainingTime, filterAttentionItems, generateAnchorElementId, performSmoothShuttle
 *
 * [POS]
 * Pure computation and DOM navigation helper for Item 189: AttentionHubNotificationQueueAndInterventionBadgeSuite.
 * Deterministically sorts multi-task attention items, calculates countdowns, and executes
 * high-precision focus shuttle jumps to target message/approval nodes.
 */

import type {
  AttentionItem,
  AttentionPriority,
  AttentionCategory,
  AttentionCategoryMeta,
  AttentionFilterState,
} from './attentionHubTypes';

export function computePriorityWeight(priority: AttentionPriority): number {
  switch (priority) {
    case 'urgent': {
      return 4;
    }
    case 'high': {
      return 3;
    }
    case 'medium': {
      return 2;
    }
    case 'info': {
      return 1;
    }
    default: {
      return 0;
    }
  }
}

export function sortAttentionItems(items: readonly AttentionItem[]): AttentionItem[] {
  return [...items].sort((a, b) => {
    // 1. Action-required items precede purely informational ones
    if (a.actionRequired !== b.actionRequired) {
      return a.actionRequired ? -1 : 1;
    }

    // 2. Higher priority first
    const weightA = computePriorityWeight(a.priority);
    const weightB = computePriorityWeight(b.priority);
    if (weightA !== weightB) {
      return weightB - weightA;
    }

    // 3. Fresher timestamp first
    return b.timestamp - a.timestamp;
  });
}

export function getCategoryMeta(category: AttentionCategory): AttentionCategoryMeta {
  switch (category) {
    case 'approval_blocking': {
      return {
        category,
        label: '待审批',
        badgeColor: 'rose',
      };
    }
    case 'clarification_needed': {
      return {
        category,
        label: '待答复',
        badgeColor: 'amber',
      };
    }
    case 'task_failed': {
      return {
        category,
        label: '任务异常',
        badgeColor: 'orange',
      };
    }
    case 'task_completed': {
      return {
        category,
        label: '任务已完成',
        badgeColor: 'emerald',
      };
    }
  }
}

export function formatRemainingTime(expiresAt?: number, now: number = Date.now()): string | null {
  if (!expiresAt) {
    return null;
  }

  const diffMs = expiresAt - now;
  if (diffMs <= 0) {
    return '已超时';
  }

  const diffSeconds = Math.floor(diffMs / 1000);
  if (diffSeconds < 60) {
    return `${diffSeconds}秒后超时`;
  }

  const diffMinutes = Math.floor(diffSeconds / 60);
  if (diffMinutes < 60) {
    return `${diffMinutes}分后超时`;
  }

  const diffHours = Math.floor(diffMinutes / 60);
  return `${diffHours}小时后超时`;
}

export function filterAttentionItems(
  items: readonly AttentionItem[],
  filter: AttentionFilterState,
): AttentionItem[] {
  const query = filter.searchQuery.trim().toLowerCase();

  return items.filter((item) => {
    if (filter.category !== 'all' && item.category !== filter.category) {
      return false;
    }

    if (filter.onlyActionRequired && !item.actionRequired) {
      return false;
    }

    if (query) {
      const matchTitle = item.title.toLowerCase().includes(query);
      const matchDesc = item.description.toLowerCase().includes(query);
      const matchChat = item.chatTitle.toLowerCase().includes(query);
      if (!matchTitle && !matchDesc && !matchChat) {
        return false;
      }
    }

    return true;
  });
}

export function generateAnchorElementId(chatId: string, anchorNodeId?: string): string {
  if (anchorNodeId) {
    return anchorNodeId;
  }
  return `chat-session-${chatId}`;
}

export function performSmoothShuttle(targetElementId: string): boolean {
  if (typeof document === 'undefined') {
    return false;
  }

  const el = document.getElementById(targetElementId);
  if (!el) {
    return false;
  }

  if (typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }

  // Flash highlight ring
  el.classList.add('ring-2', 'ring-rose-500', 'transition-all');
  setTimeout(() => {
    el.classList.remove('ring-2', 'ring-rose-500', 'transition-all');
  }, 2000);

  return true;
}
