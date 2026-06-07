'use client';

import { useState } from 'react';
import { Input } from '@/components/primitives/input';
import { Button } from '@/components/primitives/button';
import { IconX, IconPlus } from '@/components/features/icons/PremiumIcons';
import type { DmPolicy, GroupPolicy, GroupTriggerMode, GroupTriggerConfig } from '@/services/channels';

export const DM_POLICIES: DmPolicy[] = ['allowlist', 'pairing', 'open', 'disabled'];
export const GROUP_POLICIES: GroupPolicy[] = ['disabled', 'allowlist', 'open'];

export function dmPolicyLabel(policy: DmPolicy, t: (key: string) => string): string {
  const map: Record<DmPolicy, string> = {
    disabled: t('policyDisabled'),
    open: t('policyOpen'),
    allowlist: t('policyAllowlist'),
    pairing: t('policyPairing'),
  };
  return map[policy];
}

export function groupPolicyLabel(policy: GroupPolicy, t: (key: string) => string): string {
  const map: Record<GroupPolicy, string> = {
    disabled: t('policyDisabled'),
    open: t('policyOpen'),
    allowlist: t('policyAllowlist'),
  };
  return map[policy];
}

export interface ChannelOverrides {
  dmPolicy?: DmPolicy;
  groupPolicy?: GroupPolicy;
}

export interface PolicySelectorProps {
  dmPolicy: DmPolicy;
  groupPolicy: GroupPolicy;
  groupTrigger: GroupTriggerConfig;
  onDmPolicyChange: (policy: DmPolicy) => void;
  onGroupPolicyChange: (policy: GroupPolicy) => void;
  onGroupTriggerChange: (trigger: GroupTriggerConfig) => void;
  saving: boolean;
  t: (key: string) => string;
}

const TRIGGER_MODES: GroupTriggerMode[] = ['mention_only', 'prefix', 'all'];

export function PolicySelector({
  dmPolicy,
  groupPolicy,
  groupTrigger,
  onDmPolicyChange,
  onGroupPolicyChange,
  onGroupTriggerChange,
  saving,
  t,
}: PolicySelectorProps) {
  const dmLabels: Record<DmPolicy, { label: string; desc: string }> = {
    disabled: { label: t('policyDisabled'), desc: t('policyDisabledDesc') },
    open: { label: t('policyOpen'), desc: t('policyOpenDesc') },
    allowlist: { label: t('policyAllowlist'), desc: t('policyAllowlistDesc') },
    pairing: { label: t('policyPairing'), desc: t('policyPairingDesc') },
  };

  const groupLabels: Record<GroupPolicy, { label: string; desc: string }> = {
    disabled: { label: t('policyDisabled'), desc: t('groupPolicyDisabledDesc') },
    open: { label: t('policyOpen'), desc: t('groupPolicyOpenDesc') },
    allowlist: { label: t('policyAllowlist'), desc: t('groupPolicyAllowlistDesc') },
  };

  return (
    <div className="space-y-6">
      <div>
        <h4 className="text-sm font-medium mb-3">{t('dmPolicyTitle')}</h4>
        <div className="space-y-3">
          {DM_POLICIES.map((policy) => (
            <label
              key={policy}
              className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                dmPolicy === policy ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/30'
              }`}
            >
              <input
                type="radio"
                name="dmPolicy"
                value={policy}
                checked={dmPolicy === policy}
                onChange={() => onDmPolicyChange(policy)}
                disabled={saving}
                className="mt-0.5 accent-primary"
              />
              <div>
                <div className="text-sm font-medium flex items-center gap-1.5">
                  {dmLabels[policy].label}
                  {policy === 'pairing' && (
                    <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-primary/10 text-primary">
                      {t('recommended')}
                    </span>
                  )}
                </div>
                <div className="text-xs text-muted-foreground">{dmLabels[policy].desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      <div>
        <h4 className="text-sm font-medium mb-3">{t('groupPolicyTitle')}</h4>
        <div className="space-y-3">
          {GROUP_POLICIES.map((policy) => (
            <label
              key={policy}
              className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
                groupPolicy === policy
                  ? 'border-primary bg-primary/5'
                  : 'border-border hover:border-muted-foreground/30'
              }`}
            >
              <input
                type="radio"
                name="groupPolicy"
                value={policy}
                checked={groupPolicy === policy}
                onChange={() => onGroupPolicyChange(policy)}
                disabled={saving}
                className="mt-0.5 accent-primary"
              />
              <div>
                <div className="text-sm font-medium">{groupLabels[policy].label}</div>
                <div className="text-xs text-muted-foreground">{groupLabels[policy].desc}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {groupPolicy !== 'disabled' && (
        <GroupTriggerSelector trigger={groupTrigger} onChange={onGroupTriggerChange} saving={saving} t={t} />
      )}
    </div>
  );
}

// ─── Group Trigger Selector ─────────────────────────────────────────

function GroupTriggerSelector({
  trigger,
  onChange,
  saving,
  t,
}: {
  trigger: GroupTriggerConfig;
  onChange: (trigger: GroupTriggerConfig) => void;
  saving: boolean;
  t: (key: string) => string;
}) {
  const [newPrefix, setNewPrefix] = useState('');

  const triggerLabels: Record<GroupTriggerMode, { label: string; desc: string }> = {
    mention_only: { label: t('triggerMentionOnly'), desc: t('triggerMentionOnlyDesc') },
    prefix: { label: t('triggerPrefix'), desc: t('triggerPrefixDesc') },
    all: { label: t('triggerAll'), desc: t('triggerAllDesc') },
  };

  const handleAddPrefix = () => {
    const trimmed = newPrefix.trim();
    if (!trimmed) return;
    const prefixes = [...(trigger.prefixes ?? [])];
    if (!prefixes.includes(trimmed)) {
      prefixes.push(trimmed);
      onChange({ ...trigger, prefixes });
    }
    setNewPrefix('');
  };

  const handleRemovePrefix = (prefix: string) => {
    const prefixes = (trigger.prefixes ?? []).filter((p) => p !== prefix);
    onChange({ ...trigger, prefixes });
  };

  return (
    <div>
      <h4 className="text-sm font-medium mb-3">{t('triggerTitle')}</h4>
      <div className="space-y-3">
        {TRIGGER_MODES.map((mode) => (
          <label
            key={mode}
            className={`flex items-start gap-3 rounded-lg border p-3 cursor-pointer transition-colors ${
              trigger.mode === mode ? 'border-primary bg-primary/5' : 'border-border hover:border-muted-foreground/30'
            }`}
          >
            <input
              type="radio"
              name="groupTrigger"
              value={mode}
              checked={trigger.mode === mode}
              onChange={() => onChange({ ...trigger, mode })}
              disabled={saving}
              className="mt-0.5 accent-primary"
            />
            <div>
              <div className="text-sm font-medium">{triggerLabels[mode].label}</div>
              <div className="text-xs text-muted-foreground">{triggerLabels[mode].desc}</div>
            </div>
          </label>
        ))}
      </div>

      {trigger.mode === 'prefix' && (
        <div className="mt-3 space-y-2">
          <p className="text-xs text-muted-foreground">{t('triggerPrefixHint')}</p>
          <div className="flex flex-wrap gap-2">
            {(trigger.prefixes ?? []).map((prefix) => (
              <span
                key={prefix}
                className="inline-flex items-center gap-1 rounded-full bg-muted px-2 py-1 text-xs font-medium"
              >
                <code>{prefix}</code>
                <button
                  type="button"
                  onClick={() => handleRemovePrefix(prefix)}
                  disabled={saving}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <IconX className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <Input
              value={newPrefix}
              onChange={(e) => setNewPrefix(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), handleAddPrefix())}
              placeholder={t('triggerPrefixPlaceholder')}
              className="h-8 text-xs flex-1"
              disabled={saving}
            />
            <Button
              variant="outline"
              size="sm"
              onClick={handleAddPrefix}
              disabled={saving || !newPrefix.trim()}
              className="h-8"
            >
              <IconPlus className="h-3 w-3 mr-1" />
              {t('triggerPrefixAdd')}
            </Button>
          </div>
        </div>
      )}

      <p className="text-xs text-muted-foreground mt-2">{t('triggerMentionOverrideHint')}</p>
    </div>
  );
}
