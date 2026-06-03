'use client';

import { IconShieldAlert, IconZap, IconExternalLink } from '@/components/features/icons/PremiumIcons';
import { DM_POLICIES, GROUP_POLICIES, dmPolicyLabel, groupPolicyLabel } from './DmPolicySelector';
import type { ChannelOverrides } from './DmPolicySelector';
import { PairingManager } from './PairingManager';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import type { DmPolicy, GroupPolicy, GroupTriggerConfig } from '@/services/channels';

export interface ChannelPolicyOverrideProps {
  channel: string;
  globalDmPolicy: DmPolicy;
  globalGroupPolicy: GroupPolicy;
  globalGroupTrigger: GroupTriggerConfig;
  overrides: ChannelOverrides | undefined;
  onOverride: (channel: string, overrides: ChannelOverrides | undefined) => void;
  pairings: Parameters<typeof PairingManager>[0]['pairings'];
  pairingsLoading: boolean;
  onAddPairing: (channel: string, senderId: string) => Promise<void>;
  onDeletePairing: (id: string) => Promise<void>;
  onUpdatePairingStatus: (id: string, status: 'active' | 'blocked') => Promise<void>;
  onUpdatePairingDisplayName?: (id: string, displayName: string) => Promise<void>;
  saving: boolean;
  t: (key: string, values?: Record<string, string | number>) => string;
}

export function ChannelPolicyOverride({
  channel,
  globalDmPolicy,
  globalGroupPolicy,
  globalGroupTrigger,
  overrides,
  onOverride,
  pairings,
  pairingsLoading,
  onAddPairing,
  onDeletePairing,
  onUpdatePairingStatus,
  onUpdatePairingDisplayName,
  saving,
  t,
}: ChannelPolicyOverrideProps) {
  const effectiveDm = overrides?.dmPolicy ?? globalDmPolicy;
  const effectiveGroup = overrides?.groupPolicy ?? globalGroupPolicy;
  const showPairings = effectiveDm === 'allowlist' || effectiveDm === 'pairing';
  const channelPairingCount = pairings.filter((p) => p.channel === channel).length;
  const emptyAllowlist = effectiveDm === 'allowlist' && !pairingsLoading && channelPairingCount === 0;

  const updateOverride = (field: keyof ChannelOverrides, value: string) => {
    const resolved = value === '__inherit__' ? undefined : value;
    const next: ChannelOverrides = { ...overrides, [field]: resolved };
    onOverride(channel, next.dmPolicy || next.groupPolicy ? next : undefined);
  };

  const groupTriggerLabel = (mode: string) => {
    const labels: Record<string, string> = {
      mention_only: t('triggerMentionOnly'),
      prefix: t('triggerPrefix'),
      all: t('triggerAll'),
    };
    return labels[mode] || mode;
  };

  return (
    <div className="border-t pt-4 space-y-4">
      <h4 className="text-sm font-medium">{t('channelOverrideTitle')}</h4>
      <p className="text-xs text-muted-foreground">{t('channelOverrideDesc')}</p>

      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('dmPolicyTitle')}</label>
          <Select
            value={overrides?.dmPolicy ?? '__inherit__'}
            onValueChange={(v) => updateOverride('dmPolicy', v)}
            disabled={saving}
          >
            <SelectTrigger className="h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__inherit__">
                {t('inheritGlobal', { policy: dmPolicyLabel(globalDmPolicy, t) })}
              </SelectItem>
              {DM_POLICIES.map((p) => (
                <SelectItem key={p} value={p}>
                  {dmPolicyLabel(p, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <label className="text-xs font-medium text-muted-foreground">{t('groupPolicyTitle')}</label>
          <Select
            value={overrides?.groupPolicy ?? '__inherit__'}
            onValueChange={(v) => updateOverride('groupPolicy', v)}
            disabled={saving}
          >
            <SelectTrigger className="h-9 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="__inherit__">
                {t('inheritGlobal', { policy: groupPolicyLabel(globalGroupPolicy, t) })}
              </SelectItem>
              {GROUP_POLICIES.map((p) => (
                <SelectItem key={p} value={p}>
                  {groupPolicyLabel(p, t)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {effectiveDm !== 'disabled' && effectiveGroup !== 'disabled' && (
        <p className="text-xs text-muted-foreground">
          {t('effectivePolicy', {
            dm: dmPolicyLabel(effectiveDm, t),
            group: groupPolicyLabel(effectiveGroup, t),
          })}
        </p>
      )}

      {effectiveGroup !== 'disabled' && (
        <div
          className="rounded-lg border border-blue-500/30 bg-blue-500/5 p-3 space-y-2 hover:shadow-md transition-shadow"
          role="region"
          aria-label="Current Group Trigger Configuration"
        >
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-center gap-2">
              <IconZap className="h-4 w-4 text-blue-600 dark:text-blue-400 shrink-0" />
              <h5 className="text-xs font-medium text-blue-900 dark:text-blue-100">{t('currentGroupTrigger')}</h5>
            </div>
            <button
              type="button"
              onClick={() => {
                const policySection = document.querySelector('[data-section="policy"]');
                policySection?.scrollIntoView({ behavior: 'smooth', block: 'center' });
              }}
              className="flex items-center gap-1 text-xs text-blue-600 dark:text-blue-400 hover:underline shrink-0"
              aria-label="Edit global configuration"
            >
              {t('editGlobal')}
              <IconExternalLink className="h-3 w-3" />
            </button>
          </div>
          <p className="text-sm text-blue-800 dark:text-blue-200 font-medium">
            {groupTriggerLabel(globalGroupTrigger.mode)}
            {globalGroupTrigger.mode === 'prefix' &&
              globalGroupTrigger.prefixes &&
              globalGroupTrigger.prefixes.length > 0 &&
              ` (${globalGroupTrigger.prefixes.join(', ')})`}
          </p>
          <p className="text-xs text-blue-700/70 dark:text-blue-300/70">{t('followsGlobalConfig')}</p>
        </div>
      )}

      {showPairings && (
        <div className="space-y-2 pt-2">
          <h5 className="text-xs font-medium">{t('pairingTitle')}</h5>
          <p className="text-xs text-muted-foreground">{t('pairingDesc')}</p>
          {emptyAllowlist && (
            <div className="flex items-start gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5">
              <IconShieldAlert className="h-4 w-4 mt-0.5 shrink-0 text-amber-600" />
              <p className="text-xs text-amber-700 dark:text-amber-400">{t('emptyAllowlistWarning')}</p>
            </div>
          )}
          <PairingManager
            pairings={pairings}
            loading={pairingsLoading}
            fixedChannel={channel}
            mode={effectiveDm === 'pairing' ? 'pairing' : 'allowlist'}
            onAdd={onAddPairing}
            onDelete={onDeletePairing}
            onUpdateStatus={onUpdatePairingStatus}
            onUpdateDisplayName={onUpdatePairingDisplayName}
            t={t}
          />
        </div>
      )}
    </div>
  );
}
