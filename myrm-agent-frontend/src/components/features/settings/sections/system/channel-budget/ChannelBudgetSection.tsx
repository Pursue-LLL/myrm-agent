'use client';

/**
 * [INPUT]
 * - @/services/budget (POS: Channel budget API service)
 * - @/components/features/app-shell/confirm-dialog (POS: Shared confirmation dialog)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 * - @/components/primitives/alert, button, skeleton (POS: UI primitives)
 * - ../../SettingsSection (POS: Titled section of the settings page)
 * - ./useChannelBudgets (POS: Channel list data source)
 * - ./useKnownChannelGroups (POS: Groups the add form can offer)
 * - ./useChannelAudit (POS: Audit state of the unfolded channel)
 * - ./ChannelBudgetCard (POS: One channel of the panel)
 * - ./ChannelBudgetAddForm (POS: Form that adds a channel)
 *
 * [OUTPUT]
 * - ChannelBudgetSection: Settings panel for per-channel budget quotas.
 *
 * [POS]
 * Per-channel budget configuration UI. Displays each channel's daily budget usage and allows configuring per-channel
 * limits to prevent cost explosion. Each edit is sent as a patch of the one field it changes, so edits made close
 * together, or from another page, do not put each other's values back, and every write, stored or refused, is followed
 * by reading the list back: a refused write often means the list on screen is out of date. The panel says nothing about
 * its contents before the server has answered: placeholders while the first list loads, a notice with Retry when it
 * cannot be loaded (a list already on screen stays), the empty text only for a list that loaded empty. Opening the add
 * form asks for the groups on record, which the form offers apart from those that already have a channel. Deleting a
 * channel removes its guard, so the trash button only asks and the channel is deleted once the user confirms.
 */

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { ConfirmDialog } from '@/components/features/app-shell/confirm-dialog';
import { IconAlertCircle, IconPlus } from '@/components/features/icons/PremiumIcons';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { Button } from '@/components/primitives/button';
import { Skeleton } from '@/components/primitives/skeleton';
import {
  createChannelBudget,
  deleteChannelBudget,
  updateChannelBudget,
  type ChannelBudgetPolicyFields,
  type ChannelBudgetStatus,
} from '@/services/budget';
import SettingsSection from '../../SettingsSection';
import ChannelBudgetAddForm from './ChannelBudgetAddForm';
import ChannelBudgetCard from './ChannelBudgetCard';
import { useChannelAudit } from './useChannelAudit';
import { useChannelBudgets } from './useChannelBudgets';
import { useKnownChannelGroups } from './useKnownChannelGroups';

// Mirrors a channel card so the list does not jump when the first answer arrives.
function ChannelBudgetCardSkeleton() {
  return (
    <div aria-hidden className="p-3 rounded-lg border border-border/50 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <Skeleton className="h-4 w-32" />
        <Skeleton className="h-4 w-24" />
      </div>
      <Skeleton className="h-1.5 w-full rounded-full" />
      <Skeleton className="h-6 w-44" />
    </div>
  );
}

// When a list is still on screen the notice says it may be out of date.
function LoadFailedNotice({ showsStaleList, onRetry }: { showsStaleList: boolean; onRetry: () => void }) {
  const t = useTranslations('settings.channelBudget');
  const tCommon = useTranslations('common');
  return (
    <Alert variant="warning">
      <IconAlertCircle className="h-4 w-4" />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <AlertTitle>{t('loadFailedTitle')}</AlertTitle>
          <AlertDescription>{t(showsStaleList ? 'loadFailedStaleDesc' : 'loadFailedDesc')}</AlertDescription>
        </div>
        <Button type="button" variant="secondary" size="sm" className="w-full shrink-0 sm:w-auto" onClick={onRetry}>
          {tCommon('retry')}
        </Button>
      </div>
    </Alert>
  );
}

const ChannelBudgetSection = memo(() => {
  const t = useTranslations('settings.channelBudget');
  const { policies, statuses, loadStatus, refresh, retry } = useChannelBudgets();
  const knownGroups = useKnownChannelGroups();
  const audit = useChannelAudit();
  const [adding, setAdding] = useState(false);
  // The channel stays after the dialog has closed, so that its text does not change while the dialog fades out.
  const [deleteAsk, setDeleteAsk] = useState<{ channel: ChannelBudgetStatus; open: boolean } | null>(null);

  // A group that already has a channel is not offered again; `null` leaves the picker out until the answer is in.
  const channelKeysOnScreen = new Set(statuses.map((status) => status.channel_key));
  const pickableGroupKeys =
    knownGroups.status === 'ready' ? knownGroups.channelKeys.filter((key) => !channelKeysOnScreen.has(key)) : null;

  const openAddForm = () => {
    setAdding(true);
    void knownGroups.load();
  };

  // Runs a write and reads the list back whether or not it was stored; resolves to whether it was. A refused write has
  // already been reported by apiRequest.
  const settle = async (write: () => Promise<unknown>): Promise<boolean> => {
    try {
      await write();
      return true;
    } catch {
      return false;
    } finally {
      await refresh();
    }
  };

  // Only the field the user changed is sent: the rest of the policy shown here may be older than the stored one (another
  // page, or an edit still in flight), and sending it back would undo what changed meanwhile.
  const saveChannel = async (channelKey: string, patch: Partial<ChannelBudgetPolicyFields>) => {
    await settle(() => updateChannelBudget(channelKey, patch));
  };

  const deleteChannel = async (channelKey: string) => {
    await settle(() => deleteChannelBudget(channelKey));
  };

  const createChannel = (channelKey: string, policy: ChannelBudgetPolicyFields) =>
    settle(() => createChannelBudget(channelKey, policy));

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
      action={
        !adding ? (
          <button
            onClick={openAddForm}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
          >
            <IconPlus className="w-3.5 h-3.5" />
            {t('add')}
          </button>
        ) : null
      }
    >
      <ChannelBudgetAddForm
        open={adding}
        onClose={() => setAdding(false)}
        knownGroupKeys={pickableGroupKeys}
        onCreate={createChannel}
      />

      {loadStatus === 'failed' && <LoadFailedNotice showsStaleList={statuses.length > 0} onRetry={retry} />}

      {loadStatus === 'loading' &&
        statuses.length === 0 &&
        [0, 1].map((placeholder) => <ChannelBudgetCardSkeleton key={placeholder} />)}

      {loadStatus === 'ready' && statuses.length === 0 && !adding && (
        <div className="text-sm text-muted-foreground py-4 text-center">{t('empty')}</div>
      )}

      {statuses.map((status) => (
        <ChannelBudgetCard
          key={status.channel_key}
          status={status}
          policy={policies.find((p) => p.channel_key === status.channel_key)}
          audit={audit.viewOf(status.channel_key)}
          onSave={(patch) => saveChannel(status.channel_key, patch)}
          onToggleAudit={() => audit.toggle(status.channel_key)}
          onRequestDelete={() => setDeleteAsk({ channel: status, open: true })}
        />
      ))}

      <ConfirmDialog
        open={deleteAsk?.open ?? false}
        onOpenChange={(open) => setDeleteAsk((current) => (current ? { ...current, open } : current))}
        title={t('deleteConfirmTitle')}
        description={
          deleteAsk
            ? t('deleteConfirmDescription', { name: deleteAsk.channel.label || deleteAsk.channel.channel_key })
            : ''
        }
        confirmText={t('delete')}
        cancelText={t('cancel')}
        onConfirm={async () => {
          if (deleteAsk) {
            await deleteChannel(deleteAsk.channel.channel_key);
          }
        }}
      />
    </SettingsSection>
  );
});

ChannelBudgetSection.displayName = 'ChannelBudgetSection';

export default ChannelBudgetSection;
