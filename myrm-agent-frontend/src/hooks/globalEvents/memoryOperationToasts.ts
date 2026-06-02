import type { AppRouterInstance } from 'next/dist/shared/lib/app-router-context.shared-runtime';

import { toast } from '@/lib/utils/toast';

export type MemoryOperationToastTranslator = (key: string, values?: Record<string, string | number>) => string;

export interface MemoryOperationToastDeps {
  t: MemoryOperationToastTranslator;
  router: Pick<AppRouterInstance, 'push'>;
}

const MEMORY_SHARED_TAB_PATH = '/settings/memory?tab=shared';

export function showMemoryOperationToasts(data: Record<string, unknown>, deps: MemoryOperationToastDeps): void {
  const { t, router } = deps;
  const operation = String(data.operation ?? '');
  const autoApproved = data.auto_approved === true;
  const contextName = String(data.context_name ?? '').trim();

  const openSharedContextInbox = () => {
    router.push(MEMORY_SHARED_TAB_PATH);
  };

  if (operation === 'goal_completion_consolidation') {
    const decisionCount = typeof data.decision_count === 'number' ? data.decision_count : 0;
    if (autoApproved) {
      toast.success(t('goalMemoryArchived', { count: decisionCount }), {
        description: contextName || undefined,
        duration: 8_000,
        dismissible: true,
      });
      return;
    }
    toast.info(t('goalMemoryPendingApproval', { count: decisionCount }), {
      description: contextName || undefined,
      duration: 8_000,
      dismissible: true,
      action: {
        label: t('reviewSharedContextProposal'),
        onClick: openSharedContextInbox,
      },
    });
    return;
  }

  if (operation === 'correction_propagation') {
    if (autoApproved) {
      toast.success(t('correctionMemorySynced'), {
        description: contextName || undefined,
        duration: 8_000,
        dismissible: true,
      });
      return;
    }
    toast.info(t('correctionMemoryPendingApproval'), {
      description: contextName || undefined,
      duration: 8_000,
      dismissible: true,
      action: {
        label: t('reviewSharedContextProposal'),
        onClick: openSharedContextInbox,
      },
    });
    return;
  }

  if (operation === 'goal_completion_consolidation_failed') {
    toast.error(t('goalMemoryArchiveFailed'), {
      duration: 10_000,
      dismissible: true,
    });
    return;
  }

  if (operation === 'frustration_skill_learned') {
    const skillName = String(data.skill_name ?? '').trim();
    const preference = String(data.preference ?? '').trim();
    toast.success(t('frustrationSkillLearned', { skillName }), {
      description: preference || undefined,
      duration: 10_000,
      dismissible: true,
    });
  }
}
