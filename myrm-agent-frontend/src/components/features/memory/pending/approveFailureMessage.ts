/**
 * [INPUT]
 * @/services/memory/pendingTargetChanged::isPendingTargetChanged (POS: detects the "suggestion is out of date" conflict)
 *
 * [OUTPUT]
 * approveFailureMessage: localized toast title/description for a failed approve action
 *
 * [POS]
 * Shared by the pending dialog, pending list and Command Center so an out-of-date suggestion
 * always reads as "out of date" instead of surfacing backend text.
 */
import { isPendingTargetChanged } from '@/services/memory/pendingTargetChanged';

type Translate = (key: 'approveFailed' | 'targetChangedTitle' | 'targetChangedDesc' | 'unknownError') => string;

export function approveFailureMessage(t: Translate, error: unknown): { title: string; description: string } {
  if (isPendingTargetChanged(error)) {
    return { title: t('targetChangedTitle'), description: t('targetChangedDesc') };
  }
  return {
    title: t('approveFailed'),
    description: error instanceof Error ? error.message : t('unknownError'),
  };
}
