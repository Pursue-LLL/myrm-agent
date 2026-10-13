/**
 * [INPUT]
 * - @/services/skill/optimization::rollbackSkillMutationBatch (POS: skill mutation batch rollback API)
 *
 * [OUTPUT]
 * - SkillManageBatchRollbackAction: undo control for a successful skill_manage_tool batch.
 *
 * [POS]
 * Progress-step action. Restores pre-mutation snapshots for the given batch_id.
 */

'use client';

import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/primitives/alert-dialog';
import { cn } from '@/lib/utils/classnameUtils';
import { ApiError } from '@/lib/api';
import { rollbackSkillMutationBatch } from '@/services/skill/optimization';
import { notifySkillContentChanged } from '@/lib/skills/skillContentSync';
import { useSkillStore } from '@/store/skill';

type SkillManageBatchRollbackActionProps = {
  batchId: string;
};

export function SkillManageBatchRollbackAction({ batchId }: SkillManageBatchRollbackActionProps) {
  const t = useTranslations('progressSteps');
  const tSkills = useTranslations('settings.skills');
  const fetchMarketSkills = useSkillStore((state) => state.fetchMarketSkills);
  const fetchLocalSkills = useSkillStore((state) => state.fetchLocalSkills);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  const handleRollback = async () => {
    if (submitting || done) {
      return;
    }
    setSubmitting(true);
    try {
      const result = await rollbackSkillMutationBatch(batchId);
      setDone(true);
      setConfirmOpen(false);
      await Promise.all([fetchMarketSkills(true), fetchLocalSkills()]);
      notifySkillContentChanged();
      const { toast } = await import('@/lib/utils/toast');
      toast.success(
        t('skillManageRollbackSuccess', {
          count: result.skills_restored,
        }),
        { duration: 5000 },
      );
    } catch (err) {
      const { toast } = await import('@/lib/utils/toast');
      const code =
        err instanceof ApiError && typeof err.data?.code === 'string' ? err.data.code : undefined;
      toast.error(
        code === 'compensation_failed'
          ? t('skillManageRollbackCompensationFailed')
          : code === 'batch_already_consumed'
            ? t('skillManageRollbackAlreadyConsumed')
            : t('skillManageRollbackFailed'),
        { duration: 8000 },
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div
        className={cn(
          'mt-2 space-y-2 rounded-lg border px-3 py-2.5 text-xs',
          'border-primary/25 bg-primary/10 text-foreground',
        )}
        onClick={(event) => event.stopPropagation()}
        role="presentation"
      >
        <p className="leading-relaxed text-foreground/85">{t('skillManageRollbackDescription')}</p>
        <button
          type="button"
          data-testid="skill-manage-rollback-button"
          disabled={submitting || done}
          onClick={(event) => {
            event.stopPropagation();
            setConfirmOpen(true);
          }}
          className={cn(
            'btn-brand-elevation inline-flex min-h-8 max-w-full items-center justify-center rounded-full px-3 py-1.5',
            'border-0 bg-primary text-xs font-medium text-primary-foreground',
            'hover:bg-primary-hover disabled:cursor-default disabled:opacity-70',
          )}
        >
          {done
            ? t('skillManageRollbackDone')
            : submitting
              ? t('skillManageRollbackSubmitting')
              : t('skillManageRollbackButton')}
        </button>
      </div>

      <AlertDialog open={confirmOpen} onOpenChange={(open) => !submitting && setConfirmOpen(open)}>
        <AlertDialogContent className="max-w-[calc(100vw-2rem)] sm:max-w-md">
          <AlertDialogHeader>
            <AlertDialogTitle>{t('skillManageRollbackConfirmTitle')}</AlertDialogTitle>
            <AlertDialogDescription>{t('skillManageRollbackConfirmDescription')}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="flex-col-reverse gap-2 sm:flex-row">
            <AlertDialogCancel disabled={submitting}>{tSkills('upload.cancel')}</AlertDialogCancel>
            <AlertDialogAction
              disabled={submitting}
              data-testid="skill-manage-rollback-confirm"
              onClick={(event) => {
                event.preventDefault();
                void handleRollback();
              }}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {t('skillManageRollbackConfirmAction')}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
