'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { IconBan, IconFolder, IconGlobe, IconPlus, IconShieldCheck, IconX } from '@/components/features/icons/PremiumIcons';
import { DOMAIN_PATTERN } from '../../system/securityPolicyUtils';
import { cn } from '@/lib/utils/classnameUtils';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Switch } from '@/components/primitives/switch';
import { Label } from '@/components/primitives/label';
import { apiRequest } from '@/lib/api';
import { HealthScoreCard, type AuditResult } from './HealthScoreCard';

const KNOWN_CAPABILITIES = [
  'web_search_tool',
  'net_fetch',
  'shell_exec',
  'file_read',
  'file_write',
  'mcp_invoke',
  'code_interpreter_tool',
] as const;

interface SecurityOverridesData {
  capabilities: string[];
  allowedRoots: string[];
  approvalTimeoutSeconds: number | null;
  networkAllowlist: string[];
  networkBlocklist: string[];
  commandDenylist: string[];
  domainHitlEnabled: boolean;
}

const EMPTY_DATA: SecurityOverridesData = {
  capabilities: [],
  allowedRoots: [],
  approvalTimeoutSeconds: null,
  networkAllowlist: [],
  networkBlocklist: [],
  commandDenylist: [],
  domainHitlEnabled: false,
};

function normalizeDomainInput(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/^https?:\/\//, '')
    .replace(/\/.*$/, '');
}

function parseOverrides(raw: Record<string, unknown> | null): SecurityOverridesData {
  if (!raw) return EMPTY_DATA;

  const caps = Array.isArray(raw.capabilities) ? (raw.capabilities as string[]) : [];

  const pp = raw.pathPolicy as Record<string, unknown> | undefined;
  const roots = Array.isArray(pp?.allowedRoots) ? (pp!.allowedRoots as string[]) : [];

  const timeout = typeof raw.approvalTimeoutSeconds === 'number' ? raw.approvalTimeoutSeconds : null;

  const allowlist = Array.isArray(raw.networkAllowlist) ? (raw.networkAllowlist as string[]) : [];
  const blocklist = Array.isArray(raw.networkBlocklist) ? (raw.networkBlocklist as string[]) : [];
  const cmdDenylist = Array.isArray(raw.commandDenylist) ? (raw.commandDenylist as string[]) : [];

  const domainHitl = raw.domainHitlEnabled === true;

  return {
    capabilities: caps,
    allowedRoots: roots,
    approvalTimeoutSeconds: timeout,
    networkAllowlist: allowlist,
    networkBlocklist: blocklist,
    commandDenylist: cmdDenylist,
    domainHitlEnabled: domainHitl,
  };
}

function serializeOverrides(data: SecurityOverridesData): Record<string, unknown> | null {
  const hasContent =
    data.capabilities.length > 0 ||
    data.allowedRoots.length > 0 ||
    data.approvalTimeoutSeconds !== null ||
    data.networkAllowlist.length > 0 ||
    data.networkBlocklist.length > 0 ||
    data.commandDenylist.length > 0 ||
    data.domainHitlEnabled;

  if (!hasContent) return null;

  const result: Record<string, unknown> = {};
  if (data.capabilities.length > 0) result.capabilities = data.capabilities;
  if (data.allowedRoots.length > 0) result.pathPolicy = { allowedRoots: data.allowedRoots };
  if (data.approvalTimeoutSeconds !== null) result.approvalTimeoutSeconds = data.approvalTimeoutSeconds;
  if (data.networkAllowlist.length > 0) result.networkAllowlist = data.networkAllowlist;
  if (data.networkBlocklist.length > 0) result.networkBlocklist = data.networkBlocklist;
  if (data.commandDenylist.length > 0) result.commandDenylist = data.commandDenylist;
  if (data.domainHitlEnabled) result.domainHitlEnabled = true;
  return result;
}

interface AgentSecurityTabProps {
  value: Record<string, unknown> | null;
  onChange: (value: Record<string, unknown> | null) => void;
  agentId?: string | null;
  saveVersion?: number;
}

export function AgentSecurityTab({ value, onChange, agentId, saveVersion }: AgentSecurityTabProps) {
  const t = useTranslations('agent.security');
  const tCap = useTranslations('cron.capability');
  const [newPath, setNewPath] = useState('');
  const [newDomain, setNewDomain] = useState('');
  const [newBlockedDomain, setNewBlockedDomain] = useState('');
  const [newCommandPattern, setNewCommandPattern] = useState('');
  const [blocklistError, setBlocklistError] = useState<string | null>(null);
  const [cmdDenylistError, setCmdDenylistError] = useState<string | null>(null);
  const [auditResult, setAuditResult] = useState<AuditResult | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);

  const data = useMemo(() => parseOverrides(value), [value]);

  useEffect(() => {
    if (!agentId) return;
    let cancelled = false;
    setAuditLoading(true);
    apiRequest<AuditResult>(`/user-agents/${agentId}/audit`, { method: 'POST', silent: true })
      .then((res) => {
        if (!cancelled) setAuditResult(res);
      })
      .catch(() => {
        if (!cancelled) setAuditResult(null);
      })
      .finally(() => {
        if (!cancelled) setAuditLoading(false);
      });
    return () => { cancelled = true; };
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

  const addRoot = useCallback(() => {
    const trimmed = newPath.trim();
    if (!trimmed || data.allowedRoots.includes(trimmed)) return;
    update({ allowedRoots: [...data.allowedRoots, trimmed] });
    setNewPath('');
  }, [newPath, data.allowedRoots, update]);

  const removeRoot = useCallback(
    (idx: number) => {
      update({ allowedRoots: data.allowedRoots.filter((_, i) => i !== idx) });
    },
    [data.allowedRoots, update],
  );

  const addDomain = useCallback(() => {
    const trimmed = newDomain.trim().toLowerCase();
    if (!trimmed || data.networkAllowlist.includes(trimmed)) return;
    update({ networkAllowlist: [...data.networkAllowlist, trimmed] });
    setNewDomain('');
  }, [newDomain, data.networkAllowlist, update]);

  const removeDomain = useCallback(
    (idx: number) => {
      update({ networkAllowlist: data.networkAllowlist.filter((_, i) => i !== idx) });
    },
    [data.networkAllowlist, update],
  );

  const addBlockedDomain = useCallback(() => {
    const normalized = normalizeDomainInput(newBlockedDomain);
    if (!normalized) return;
    if (!DOMAIN_PATTERN.test(normalized)) {
      setBlocklistError(t('invalidBlockedDomain'));
      return;
    }
    if (data.networkBlocklist.includes(normalized)) {
      setBlocklistError(t('duplicateBlockedDomain'));
      return;
    }
    setBlocklistError(null);
    update({ networkBlocklist: [...data.networkBlocklist, normalized] });
    setNewBlockedDomain('');
  }, [newBlockedDomain, data.networkBlocklist, update, t]);

  const removeBlockedDomain = useCallback(
    (idx: number) => {
      setBlocklistError(null);
      update({ networkBlocklist: data.networkBlocklist.filter((_, i) => i !== idx) });
    },
    [data.networkBlocklist, update],
  );

  const addCommandPattern = useCallback(() => {
    const trimmed = newCommandPattern.trim();
    if (!trimmed) return;
    if (data.commandDenylist.includes(trimmed)) {
      setCmdDenylistError(t('duplicateCommandPattern', { default: 'Pattern already exists.' }));
      return;
    }
    setCmdDenylistError(null);
    update({ commandDenylist: [...data.commandDenylist, trimmed] });
    setNewCommandPattern('');
  }, [newCommandPattern, data.commandDenylist, update, t]);

  const removeCommandPattern = useCallback(
    (idx: number) => {
      setCmdDenylistError(null);
      update({ commandDenylist: data.commandDenylist.filter((_, i) => i !== idx) });
    },
    [data.commandDenylist, update],
  );

  const handleFixNavigate = useCallback((targetId: string) => {
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
  }, [update]);

  return (
    <div className={cn('space-y-5', 'animate-in fade-in-50 duration-300')}>
      {/* Health Score Card */}
      {agentId && (
        <HealthScoreCard result={auditResult} loading={auditLoading} t={t} onFixToggle={handleFixNavigate} />
      )}

      {/* Capabilities */}
      <div id="capabilities-section" className="rounded-xl border border-border bg-card p-4 space-y-3 transition-all duration-300">
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
      <div id="allowed-roots-section" className="rounded-xl border border-border bg-card p-4 space-y-3 transition-all duration-300">
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconFolder className="h-4 w-4 text-primary" />
            {t('allowedRootsTitle')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('allowedRootsDesc')}</p>
        </div>

        {data.allowedRoots.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.allowedRoots.map((root, idx) => (
              <div
                key={`${root}-${idx}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-primary/10 border border-primary/30"
              >
                <code className="text-xs text-primary font-mono">{root}</code>
                <button
                  type="button"
                  onClick={() => removeRoot(idx)}
                  className="text-primary/60 hover:text-destructive transition-colors"
                >
                  <IconX className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2">
          <Input
            placeholder={t('pathPlaceholder')}
            value={newPath}
            onChange={(e) => setNewPath(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addRoot();
              }
            }}
            className="flex-1 text-sm"
          />
          <Button variant="outline" size="sm" onClick={addRoot} disabled={!newPath.trim()}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addPath')}
          </Button>
        </div>

        {data.allowedRoots.length === 0 && (
          <p className="text-xs text-muted-foreground/70 italic">{t('noAllowedRoots')}</p>
        )}
      </div>

      {/* Network Domain Allowlist */}
      <div id="network-allowlist-section" className="rounded-xl border border-border bg-card p-4 space-y-3 transition-all duration-300">
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconGlobe className="h-4 w-4 text-primary" />
            {t('networkAllowlistTitle')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('networkAllowlistDesc')}</p>
        </div>

        {data.networkAllowlist.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.networkAllowlist.map((domain, idx) => (
              <div
                key={`${domain}-${idx}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30"
              >
                <code className="text-xs text-emerald-700 dark:text-emerald-400 font-mono">{domain}</code>
                <button
                  type="button"
                  onClick={() => removeDomain(idx)}
                  className="text-emerald-500/60 hover:text-destructive transition-colors"
                >
                  <IconX className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex items-center gap-2">
          <Input
            placeholder={t('domainPlaceholder')}
            value={newDomain}
            onChange={(e) => setNewDomain(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addDomain();
              }
            }}
            className="flex-1 text-sm"
          />
          <Button variant="outline" size="sm" onClick={addDomain} disabled={!newDomain.trim()}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addDomain')}
          </Button>
        </div>

        {data.networkAllowlist.length === 0 && (
          <p className="text-xs text-muted-foreground/70 italic">{t('noNetworkAllowlist')}</p>
        )}

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
      </div>

      {/* Network Domain Blocklist */}
      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconBan className="h-4 w-4 text-destructive" />
            {t('networkBlocklistTitle')}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">{t('networkBlocklistDesc')}</p>
        </div>

        {data.networkBlocklist.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.networkBlocklist.map((domain, idx) => (
              <div
                key={`${domain}-${idx}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-destructive/10 border border-destructive/30"
              >
                <code className="text-xs text-destructive font-mono">{domain}</code>
                <button
                  type="button"
                  onClick={() => removeBlockedDomain(idx)}
                  className="text-destructive/60 hover:text-destructive transition-colors"
                >
                  <IconX className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            placeholder={t('blockedDomainPlaceholder')}
            value={newBlockedDomain}
            onChange={(e) => {
              setNewBlockedDomain(e.target.value);
              if (blocklistError) setBlocklistError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addBlockedDomain();
              }
            }}
            className="flex-1 text-sm"
          />
          <Button variant="outline" size="sm" onClick={addBlockedDomain} disabled={!newBlockedDomain.trim()}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addBlockedDomain')}
          </Button>
        </div>

        {blocklistError && <p className="text-xs text-destructive">{blocklistError}</p>}

        {data.networkBlocklist.length === 0 && !blocklistError && (
          <p className="text-xs text-muted-foreground/70 italic">{t('noNetworkBlocklist')}</p>
        )}
      </div>

      {/* Command Deny List */}
      <div className="rounded-xl border border-border bg-card p-4 space-y-3">
        <div>
          <h3 className="text-sm font-medium text-foreground flex items-center gap-1.5">
            <IconBan className="h-4 w-4 text-destructive" />
            {t('commandDenylistTitle', { default: 'Command Deny List' })}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t('commandDenylistDesc', {
              default:
                'Commands matching these patterns will be permanently blocked, even under YOLO mode. Uses glob syntax (e.g. git push --force*).',
            })}
          </p>
        </div>

        {data.commandDenylist.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {data.commandDenylist.map((pattern, idx) => (
              <div
                key={`${pattern}-${idx}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-destructive/10 border border-destructive/30"
              >
                <IconBan className="h-3 w-3 text-destructive shrink-0" />
                <code className="text-xs text-destructive font-mono">{pattern}</code>
                <button
                  type="button"
                  onClick={() => removeCommandPattern(idx)}
                  className="text-destructive/60 hover:text-destructive transition-colors"
                >
                  <IconX className="h-3 w-3" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <Input
            placeholder={t('commandPatternPlaceholder', { default: 'e.g. git push --force* or *DROP DATABASE*' })}
            value={newCommandPattern}
            onChange={(e) => {
              setNewCommandPattern(e.target.value);
              if (cmdDenylistError) setCmdDenylistError(null);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addCommandPattern();
              }
            }}
            className="flex-1 text-sm font-mono"
          />
          <Button variant="outline" size="sm" onClick={addCommandPattern} disabled={!newCommandPattern.trim()}>
            <IconPlus className="h-4 w-4 mr-1" />
            {t('addCommandPattern', { default: 'Add' })}
          </Button>
        </div>

        {cmdDenylistError && <p className="text-xs text-destructive">{cmdDenylistError}</p>}

        {data.commandDenylist.length === 0 && !cmdDenylistError && (
          <p className="text-xs text-muted-foreground/70 italic">
            {t('noCommandDenylist', { default: 'No command restrictions — uses global policy only.' })}
          </p>
        )}
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

