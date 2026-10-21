/** Rollback action wiring for discovery install toasts.

[INPUT]
- skillDiscoverInstallToast::formatSkillInstallToast (POS: toast payload)
- @/services/skill rollback API (POS: mutation batch rollback)

[OUTPUT]
- showDiscoveryInstallResultToast: toast with optional undo for pre-replace batches

[POS]
Shared install feedback for Discover tab and URL import dialog.
*/

import { toast } from '@/hooks/shared/useToast';
import { DiscoveryInstallResponse, rollbackSkillMutationBatch } from '@/services/skill';
import {
  formatSkillInstallToast,
  SkillInstallToastCallbacks,
  toSkillInstallToastResponse,
} from './skillDiscoverInstallToast';

type TranslateFn = (key: string, params?: Record<string, string>) => string;

export type ShowDiscoveryInstallToastOptions = {
  skillName: string;
  response: DiscoveryInstallResponse;
  marketUpdate: boolean;
  t: TranslateFn;
  onInstalled?: () => void;
  extraCallbacks?: Pick<SkillInstallToastCallbacks, 'onTrialRun'>;
};

export function showDiscoveryInstallResultToast(options: ShowDiscoveryInstallToastOptions): void {
  const { skillName, response, marketUpdate, t, onInstalled, extraCallbacks } = options;
  const displayName = skillName.trim() || response.skill_name?.trim() || '';
  const toastResponse = toSkillInstallToastResponse(response, marketUpdate);
  const batchId = response.pre_replace_batch_id?.trim();

  const payload = formatSkillInstallToast(displayName, toastResponse, t, {
    ...extraCallbacks,
    onRollbackPreUpdate: batchId
      ? () => {
          void (async () => {
            try {
              const rolled = await rollbackSkillMutationBatch(batchId);
              toast({
                title: t('restorePreUpdateSuccess', { name: displayName }),
                description: t('restorePreUpdateSuccessDesc', {
                  count: String(rolled.skills_restored),
                }),
              });
              onInstalled?.();
            } catch (error) {
              const message = error instanceof Error ? error.message : '';
              toast({
                title: t('restorePreUpdateFailed'),
                description: message || t('restorePreUpdateFailedDesc'),
                variant: 'destructive',
              });
            }
          })();
        }
      : undefined,
  });
  toast(payload);
}
