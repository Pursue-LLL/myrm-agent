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

interface ApproveFailureMessage {
  title: string;
  description: string;
  variant: 'default' | 'destructive';
}

/** An out-of-date suggestion is not a malfunction, so it is shown as a plain notice rather than an error. */
export function approveFailureMessage(t: Translate, error: unknown): ApproveFailureMessage {
  if (isPendingTargetChanged(error)) {
    return { title: t('targetChangedTitle'), description: t('targetChangedDesc'), variant: 'default' };
  }
  return {
    title: t('approveFailed'),
    description: error instanceof Error ? error.message : t('unknownError'),
    variant: 'destructive',
  };
}
