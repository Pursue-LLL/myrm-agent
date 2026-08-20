import type { RunDigest } from '@/services/copilot';

export type CopilotHeadlineTranslator = (key: string, values?: Record<string, string | number>) => string;

export function resolveRunDigestHeadline(digest: RunDigest | null, t: CopilotHeadlineTranslator): string {
  if (!digest) {
    return t('runningFallback');
  }
  switch (digest.phase) {
    case 'waiting_approval':
      return t('headlineWaitingApproval', { count: digest.pending_approval_count });
    case 'running':
      if (digest.current_tool && digest.step_count > 0) {
        return t('headlineRunning', { step: digest.step_count, tool: digest.current_tool });
      }
      return t('runningFallback');
    case 'completed':
      return t('headlineCompleted', { count: digest.step_count });
    case 'error':
      return t('headlineFailed');
    case 'cancelled':
      return t('headlineCancelled');
    default:
      return t('runningFallback');
  }
}
