'use client';

/**
 * [INPUT]
 * - @/services/sshVault (POS: SSH Vault API client and models)
 * - @phosphor-icons/react (POS: Secure iconography)
 * - BreakGlassModal (POS: Emergency change window authorization dialog)
 *
 * [OUTPUT]
 * - SSHVaultPanel: UI panel managing SSH host assets, read-only gates, probe testing, and break-glass.
 *
 * [POS]
 * Integrated into settings credentials tab under integration sections.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  ArrowsClockwise,
  Check,
  CheckCircle,
  Copy,
  Globe,
  LockKey,
  LockKeyOpen,
  Pulse,
  ShieldCheck,
  WarningCircle,
} from '@phosphor-icons/react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/hooks/shared/useToast';
import {
  getSSHVaultSummary,
  probeSSHHost,
  updateHostPolicy,
  type SSHAssetSummary,
  type SSHHostConfig,
  type SSHProbeResult,
} from '@/services/sshVault';
import { BreakGlassModal } from './BreakGlassModal';

export function SSHVaultPanel() {
  const t = useTranslations('settings.sshVault');
  const [summary, setSummary] = useState<SSHAssetSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [probingHosts, setProbingHosts] = useState<Record<string, boolean>>({});
  const [probeResults, setProbeResults] = useState<Record<string, SSHProbeResult>>({});
  const [copiedHost, setCopiedHost] = useState<string | null>(null);

  // Break-glass modal state
  const [breakGlassHost, setBreakGlassHost] = useState<string | null>(null);

  const loadSummary = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await getSSHVaultSummary();
      setSummary(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast({
        title: msg,
        variant: 'destructive',
      });
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const handleProbe = async (hostAlias: string) => {
    try {
      setProbingHosts((prev) => ({ ...prev, [hostAlias]: true }));
      const result = await probeSSHHost(hostAlias);
      setProbeResults((prev) => ({ ...prev, [hostAlias]: result }));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast({
        title: `Probe failed for ${hostAlias}: ${msg}`,
        variant: 'destructive',
      });
    } finally {
      setProbingHosts((prev) => ({ ...prev, [hostAlias]: false }));
    }
  };

  const handleToggleReadOnly = async (host: SSHHostConfig) => {
    const newReadOnly = !host.is_read_only;
    try {
      await updateHostPolicy(host.host_alias, { is_read_only: newReadOnly });
      setSummary((prev) => {
        if (!prev) return prev;
        return {
          ...prev,
          hosts: prev.hosts.map((h) =>
            h.host_alias === host.host_alias ? { ...h, is_read_only: newReadOnly } : h,
          ),
        };
      });
      toast({
        title: `${host.host_alias}: ${t('policyUpdated')}`,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      toast({
        title: msg,
        variant: 'destructive',
      });
    }
  };

  const handleCopyPrompt = async (host: SSHHostConfig) => {
    const prompt = `Use remote SSH host "${host.host_alias}" (${host.hostname}) to inspect and perform maintenance diagnostics.`;
    try {
      await navigator.clipboard.writeText(prompt);
      setCopiedHost(host.host_alias);
      setTimeout(() => setCopiedHost(null), 2000);
      toast({
        title: t('copied'),
      });
    } catch {
      toast({
        title: t('copyFailed'),
        variant: 'destructive',
      });
    }
  };

  const getTierBadge = (tier: string) => {
    switch (tier?.toLowerCase()) {
      case 'production':
        return (
          <Badge variant="outline" className="border-red-500/40 text-red-600 dark:text-red-400 bg-red-500/10 text-xs">
            {t('tierProd')}
          </Badge>
        );
      case 'staging':
        return (
          <Badge
            variant="outline"
            className="border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10 text-xs"
          >
            {t('tierStaging')}
          </Badge>
        );
      default:
        return (
          <Badge variant="secondary" className="text-xs">
            {t('tierDev')}
          </Badge>
        );
    }
  };

  return (
    <div className="rounded-lg border p-4 bg-card/60 backdrop-blur-sm space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-medium flex items-center gap-2 text-base">
            <Globe className="h-5 w-5 text-primary" />
            {t('title')}
            {summary && (
              <Badge variant="secondary" className="ml-1 text-xs">
                {summary.total_hosts}
              </Badge>
            )}
          </h3>
          <p className="text-xs text-muted-foreground mt-0.5">
            {t('source')}: {summary?.config_path || '~/.ssh/config'}
          </p>
        </div>
        <Button size="sm" variant="ghost" onClick={loadSummary} disabled={isLoading} className="gap-1.5 text-xs">
          <ArrowsClockwise className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
          {t('refresh')}
        </Button>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          {[1, 2].map((i) => (
            <div key={i} className="flex items-center gap-3 p-3 rounded-lg border bg-muted/20 animate-pulse">
              <div className="h-8 w-8 rounded bg-muted" />
              <div className="flex-1 space-y-1.5">
                <div className="h-4 w-32 bg-muted rounded" />
                <div className="h-3 w-48 bg-muted rounded" />
              </div>
            </div>
          ))}
        </div>
      ) : !summary || summary.hosts.length === 0 ? (
        <div className="text-center py-8 text-xs text-muted-foreground border rounded-lg border-dashed">
          {t('noHosts')}
        </div>
      ) : (
        <div className="space-y-3">
          {summary.hosts.map((host) => {
            const probe = probeResults[host.host_alias];
            const isProbing = probingHosts[host.host_alias];

            return (
              <div
                key={host.host_alias}
                className="p-3 rounded-lg border bg-background/80 hover:border-primary/40 transition-colors flex flex-col sm:flex-row sm:items-center justify-between gap-3"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm font-semibold">{host.host_alias}</span>
                    {getTierBadge(host.environment_tier)}

                    {host.is_read_only ? (
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 gap-1 text-xs"
                      >
                        <ShieldCheck className="h-3.5 w-3.5 text-emerald-500" />
                        {t('readOnlyBadge')}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="border-muted text-muted-foreground gap-1 text-xs">
                        <LockKeyOpen className="h-3.5 w-3.5 text-muted-foreground" />
                        {t('writableBadge')}
                      </Badge>
                    )}

                    {probe && (
                      <span
                        className={`text-xs flex items-center gap-1 font-mono ${
                          probe.reachable ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-500'
                        }`}
                      >
                        {probe.reachable ? (
                          <>
                            <CheckCircle className="h-3.5 w-3.5" />
                            {probe.latency_ms.toFixed(1)}ms
                          </>
                        ) : (
                          <>
                            <WarningCircle className="h-3.5 w-3.5" />
                            Offline
                          </>
                        )}
                      </span>
                    )}
                  </div>

                  <div className="text-xs text-muted-foreground font-mono">
                    {host.user ? `${host.user}@` : ''}
                    {host.hostname}
                    {host.port && host.port !== 22 ? `:${host.port}` : ''}
                  </div>
                </div>

                <div className="flex items-center gap-2 flex-wrap sm:flex-nowrap shrink-0">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => handleProbe(host.host_alias)}
                    disabled={isProbing}
                    className="text-xs gap-1 h-8"
                  >
                    <Pulse className={`h-3.5 w-3.5 ${isProbing ? 'animate-pulse text-amber-500' : ''}`} />
                    {isProbing ? t('probing') : t('probe')}
                  </Button>

                  <Button
                    size="sm"
                    variant={host.is_read_only ? 'secondary' : 'outline'}
                    onClick={() => handleToggleReadOnly(host)}
                    className="text-xs gap-1 h-8"
                    title={t('readOnlyDesc')}
                  >
                    {host.is_read_only ? (
                      <LockKey className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <LockKeyOpen className="h-3.5 w-3.5" />
                    )}
                    {host.is_read_only ? t('readOnlyBadge') : t('writableBadge')}
                  </Button>

                  {host.is_read_only && (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setBreakGlassHost(host.host_alias)}
                      className="text-xs gap-1 h-8 text-amber-600 dark:text-amber-400 border-amber-500/30 hover:bg-amber-500/10"
                    >
                      <ShieldCheck className="h-3.5 w-3.5" />
                      {t('breakGlassAction')}
                    </Button>
                  )}

                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handleCopyPrompt(host)}
                    className="text-xs gap-1 h-8"
                  >
                    {copiedHost === host.host_alias ? (
                      <Check className="h-3.5 w-3.5 text-emerald-500" />
                    ) : (
                      <Copy className="h-3.5 w-3.5" />
                    )}
                    {copiedHost === host.host_alias ? t('copied') : t('copyPrompt')}
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {breakGlassHost && (
        <BreakGlassModal
          isOpen={!!breakGlassHost}
          onClose={() => setBreakGlassHost(null)}
          hostAlias={breakGlassHost}
        />
      )}
    </div>
  );
}
