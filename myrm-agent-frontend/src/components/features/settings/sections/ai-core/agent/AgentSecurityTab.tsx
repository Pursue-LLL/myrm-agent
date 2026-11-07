'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  IconBan,
  IconFolder,
  IconGlobe,
  IconShieldAlert,
  IconShieldCheck,
} from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { apiRequest } from '@/lib/api';
import { HealthScoreCard, type AuditResult } from './HealthScoreCard';
import { SecurityChipListEditor } from './SecurityChipListEditor';
import { useSecurityListEditors } from './useSecurityListEditors';
import {
  KNOWN_CAPABILITIES,
  type SecurityOverridesData,
  parseOverrides,
  serializeOverrides,
} from './agentSecurityOverrides';

interface AgentSecurityTabProps {
  value: Record<string, unknown> | null;
  onChange: (value: Record<string, unknown> | null) => void;
  defaultSecurityPreset: 'hitl' | 'accept_edits' | 'explore' | null;
  onDefaultSecurityPresetChange: (preset: 'hitl' | 'accept_edits' | 'explore' | null) => void;
  agentId?: string | null;
  saveVersion?: number;
}

const PRESET_OPTIONS = ['hitl', 'accept_edits', 'explore'] as const;

export function AgentSecurityTab({
  value,
  onChange,
  defaultSecurityPreset,
  onDefaultSecurityPresetChange,
  agentId,
  saveVersion,
}: AgentSecurityTabProps) {
  const t = useTranslations('agent.security');
  const tCap = useTranslations('cron.capability');
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);

  const data = useMemo(() => parseOverrides(value), [value]);

  useEffect(() => {
    if (!agentId) {
      return;
    }
    let cancelled = false;
    setAuditLoading(true);
    apiRequest<AuditResult>(`/user-agents/${agentId}/audit`, { method: 'POST', silent: true })
      .then((res) => {
        if (!cancelled) {
          setAuditResult(res);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setAuditResult(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setAuditLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [agentId, saveVersion]);

  const update = useCallback(
    (patch: Partial<SecurityOverridesData>) => {
      onChange(serializeOverrides({ ...data, ...patch }));
    },
    [data, onChange],
  );

  const toggleCapability = useCallback(
    (cap: string) => {
      const next = data.capabilities.includes(cap)
        ? data.capabilities.filter((c) => c !== cap)
        : [...data.capabilities, cap];
      update({ capabilities: next });
    },
    [data.capabilities, update],
  );

  const { roots, allowlist, blocklist, denylist } = useSecurityListEditors({ data, update });

  const handleFixNavigate = useCallback(
    (targetId: string) => {
      if (targetId === 'domain-hitl-switch') {
        update({ domainHitlEnabled: true });
        return;
      }
      const el = document.getElementById(targetId);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('ring-2', 'ring-primary/50');
        setTimeout(() => el.classList.remove('ring-2', 'ring-primary/50'), 2000);
      }
    },
    [update],
  );

  return (
    <div className="space-y-5 animate-in fade-in-50 duration-300">
      {/* 默认会话安全预设 */}
      <div className="rounded-xl border border-border bg-card p-4 space-y-3 transition-all duration-300">
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconShieldCheck className="h-4 w-4 text-primary" />
            {t('defaultPresetTitle')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('defaultPresetDesc')}</p>
        </div>
        <Select
          value={defaultSecurityPreset ?? 'inherit'}
          onValueChange={(v) =>
            onDefaultSecurityPresetChange(v === 'inherit' ? null : (v as 'hitl' | 'accept_edits' | 'explore'))
          }
        >
          <SelectTrigger className="w-full sm:w-72">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="inherit">{t('defaultPresetInherit')}</SelectItem>
            {PRESET_OPTIONS.map((p) => (
              <SelectItem key={p} value={p}>
                {t(`presets.${p}.label`)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Health Score Card */}
      {agentId && <HealthScoreCard result={auditResult} loading={auditLoading} t={t} onFixToggle={handleFixNavigate} />}

      {/* Capabilities */}
      <div
        id="capabilities-section"
        className="rounded-xl border border-border bg-card p-4 space-y-3 transition-all duration-300"
      >
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconShieldCheck className="h-4 w-4 text-primary" />
            {t('capabilitiesTitle')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('capabilitiesDesc')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {KNOWN_CAPABILITIES.map((cap) => {
            const selected = data.capabilities.includes(cap);
            return (
              <button
                key={cap}
                type="button"
                onClick={() => toggleCapability(cap)}
                className={cn(
                  'px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors',
                  selected
                    ? 'bg-primary/10 text-primary border-primary/40'
                    : 'bg-muted/50 text-muted-foreground border-border hover:bg-muted',
                )}
              >
                {tCap(cap)}
              </button>
            );
          })}
        </div>
        {data.capabilities.length === 0 && (
          <p className="text-xs text-muted-foreground/70 italic">{t('noCapabilities')}</p>
        )}
      </div>

      {/* Allowed Roots */}
      <SecurityChipListEditor
        scrollTargetId="allowed-roots-section"
        icon={<IconFolder className="h-4 w-4 text-primary" />}
        title={t('allowedRootsTitle')}
        description={t('allowedRootsDesc')}
        tone="primary"
        placeholder={t('pathPlaceholder')}
        addLabel={t('addPath')}
        emptyText={t('noAllowedRoots')}
        {...roots}
      />

      {/* Network Domain Allowlist */}
      <SecurityChipListEditor
        scrollTargetId="network-allowlist-section"
        icon={<IconGlobe className="h-4 w-4 text-primary" />}
        title={t('networkAllowlistTitle')}
        description={t('networkAllowlistDesc')}
        tone="success"
        placeholder={t('domainPlaceholder')}
        addLabel={t('addDomain')}
        emptyText={t('noNetworkAllowlist')}
        {...allowlist}
      >
        {/* Domain HITL Switch */}
        <div className="flex items-center justify-between pt-2 border-t border-border/50">
          <div className="space-y-0.5">
            <Label htmlFor="domain-hitl-switch" className="text-sm font-medium">
              {t('domainHitlTitle')}
            </Label>
            <p className="text-xs text-muted-foreground">{t('domainHitlDesc')}</p>
          </div>
          <Switch
            id="domain-hitl-switch"
            checked={data.domainHitlEnabled}
            onCheckedChange={(checked) => update({ domainHitlEnabled: checked })}
          />
        </div>
      </SecurityChipListEditor>

      {/* Network Domain Blocklist */}
      <SecurityChipListEditor
        icon={<IconBan className="h-4 w-4 text-destructive-text" />}
        title={t('networkBlocklistTitle')}
        description={t('networkBlocklistDesc')}
        tone="danger"
        placeholder={t('blockedDomainPlaceholder')}
        addLabel={t('addBlockedDomain')}
        emptyText={t('noNetworkBlocklist')}
        stackOnMobile
        {...blocklist}
      />

      {/* Command Deny List */}
      <SecurityChipListEditor
        icon={<IconBan className="h-4 w-4 text-destructive-text" />}
        title={t('commandDenylistTitle')}
        description={t('commandDenylistDesc')}
        tone="danger"
        chipIcon={<IconBan className="h-3 w-3 text-destructive-text shrink-0" />}
        placeholder={t('commandPatternPlaceholder')}
        addLabel={t('addCommandPattern')}
        emptyText={t('noCommandDenylist')}
        monospaceInput
        stackOnMobile
        {...denylist}
      />

      {/* Injection Policy */}
      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <div className="flex items-center justify-between">
          <div className="space-y-0.5">
            <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
              <IconShieldAlert className="h-4 w-4 text-amber-500" />
              {t('injectionPolicyTitle')}
            </h3>
            <p className="text-xs text-muted-foreground">{t('injectionPolicyDesc')}</p>
          </div>
          <Switch
            checked={data.injectionPolicy === 'fail_closed'}
            onCheckedChange={(checked) => update({ injectionPolicy: checked ? 'fail_closed' : 'log_only' })}
          />
        </div>
      </div>

      {/* Approval Timeout */}
      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <div>
          <h3 className="text-sm font-medium text-foreground">{t('timeoutTitle')}</h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('timeoutDesc')}</p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            type="number"
            min={10}
            max={600}
            placeholder={t('timeoutPlaceholder')}
            value={data.approvalTimeoutSeconds ?? ''}
            onChange={(e) => {
              const val = e.target.value;
              if (!val) {
                update({ approvalTimeoutSeconds: null });
              } else {
                update({ approvalTimeoutSeconds: Math.max(10, Math.min(600, Number(val))) });
              }
            }}
            className="w-24"
          />
          <span className="text-sm text-muted-foreground">{t('seconds')}</span>
        </div>
      </div>
    </div>
  );
}
