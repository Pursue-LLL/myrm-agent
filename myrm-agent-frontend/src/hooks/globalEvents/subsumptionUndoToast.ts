import { fetchWithTimeout } from '@/lib/api';
import { asRecord } from '@/lib/utils/typeUtils';
import type { toast } from '@/lib/utils/toast';

export type SubsumptionTranslator = (key: string, values?: Record<string, string | number>) => string;

export interface SubsumptionUndoToastDeps {
  t: SubsumptionTranslator;
  tIdle: SubsumptionTranslator;
  pushToast: { [K in 'info' | 'success' | 'error']: (...args: Parameters<(typeof toast)[K]>) => void };
}

/**
 * Offers a one-click undo after idle-time knowledge subsumption soft-deleted memories.
 * Only the `notification` status of `cognitive_subsumption` carries the restorable ids.
 */
export function showSubsumptionUndoToast(data: Record<string, unknown>, deps: SubsumptionUndoToastDeps): void {
  if (data.status !== 'notification' || data.task_name !== 'cognitive_subsumption') {
    return;
  }

  const detail = asRecord(data.data);
  const count = typeof detail.count === 'number' ? detail.count : 0;
  const subsumedIds = Array.isArray(detail.subsumed_ids) ? detail.subsumed_ids : [];
  if (count <= 0 || subsumedIds.length === 0) {
    return;
  }

  const { t, tIdle, pushToast } = deps;
  pushToast.info(tIdle('cognitive_subsumption.notification', { count }), {
    duration: 15_000,
    dismissible: true,
    action: {
      label: t('undoConsolidation'),
      onClick: async () => {
        try {
          const res = await fetchWithTimeout('/memory/undo-consolidation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ subsumed_ids: subsumedIds }),
          });
          if (!res.ok) {
            throw new Error('Undo failed');
          }
          pushToast.success(t('undoConsolidationSuccess'));
        } catch {
          pushToast.error(t('undoConsolidationFailed'));
        }
      },
    },
  });
}
