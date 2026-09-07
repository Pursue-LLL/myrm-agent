/**
 * [INPUT]
 * - lucide-react (POS: Clean iconography)
 * - next-intl::useTranslations (POS: Dual language i18n support)
 *
 * [OUTPUT]
 * - SSHHostManagerCard: Modern reactive host inventory and probing card for settings/system.
 *
 * [POS]
 * Settings section for SSH Asset Vault and host reachability monitoring.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import {
  Server,
  Terminal,
  Activity,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Copy,
  Check,
  ShieldCheck,
  Zap,
} from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

export interface SSHHostItem {
  host_alias: string;
  hostname: string;
  port: number;
  user: string;
  identity_file?: string | null;
  tags?: string[];
  description?: string | null;
}

export interface SSHProbeStatus {
  is_reachable: boolean;
  latency_ms?: number | null;
  error_message?: string | null;
}

export default function SSHHostManagerCard({ className }: { className?: string }) {
  const t = useTranslations('settings.sshVault');
  const [hosts, setHosts] = useState<SSHHostItem[]>([]);
  const [configSource, setConfigSource] = useState<string>('~/.ssh/config');
  const [loading, setLoading] = useState<boolean>(true);
  const [probingHost, setProbingHost] = useState<string | null>(null);
  const [probeResults, setProbeResults] = useState<Record<string, SSHProbeStatus>>({});
  const [copiedAlias, setCopiedAlias] = useState<string | null>(null);

  const fetchHosts = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch('/api/ssh-vault/summary');
      if (res.ok) {
        const data = await res.json();
        setHosts(data.hosts || []);
        setConfigSource(data.config_source || '~/.ssh/config');
      } else {
        // Fallback default sample for presentation
        setHosts([
          {
            host_alias: 'gpu-cluster-01',
            hostname: '192.168.1.120',
            port: 22,
            user: 'ubuntu',
            identity_file: '~/.ssh/id_rsa',
            tags: ['gpu', 'cluster'],
          },
        ]);
      }
    } catch {
      setHosts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHosts();
  }, [fetchHosts]);

  const handleProbe = async (hostAlias: string) => {
    setProbingHost(hostAlias);
    try {
      const res = await fetch(`/api/ssh-vault/probe/${encodeURIComponent(hostAlias)}?timeout=2.5`);
      if (res.ok) {
        const data = await res.json();
        setProbeResults((prev) => ({
          ...prev,
          [hostAlias]: {
            is_reachable: data.is_reachable,
            latency_ms: data.latency_ms,
            error_message: data.error_message,
          },
        }));
      } else {
        setProbeResults((prev) => ({
          ...prev,
          [hostAlias]: { is_reachable: false, error_message: 'Probe request failed' },
        }));
      }
    } catch (e: any) {
      setProbeResults((prev) => ({
        ...prev,
        [hostAlias]: { is_reachable: false, error_message: e.message || 'Network error' },
      }));
    } finally {
      setProbingHost(null);
    }
  };

  const copyPromptHint = (alias: string) => {
    const text = `连一下 ${alias} 执行命令排查状态`;
    navigator.clipboard.writeText(text);
    setCopiedAlias(alias);
    setTimeout(() => setCopiedAlias(null), 2000);
  };

  return (
    <div
      className={cn(
        'rounded-xl border border-border bg-card text-card-foreground p-5 space-y-4 shadow-sm',
        className
      )}
    >
      <div className="flex items-center justify-between border-b border-border pb-3">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-primary/10 text-primary">
            <Server className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold tracking-tight">{t('title')}</h3>
            <p className="text-xs text-muted-foreground">
              {t('source')}: <span className="font-mono text-foreground/80">{configSource}</span>
            </p>
          </div>
        </div>

        <button
          onClick={fetchHosts}
          disabled={loading}
          className="p-1.5 rounded-md hover:bg-muted text-muted-foreground hover:text-foreground transition-colors disabled:opacity-50"
          title={t('refresh')}
        >
          <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
        </button>
      </div>

      <div className="space-y-3">
        {hosts.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground rounded-lg border border-dashed border-border bg-muted/20">
            {t('noHosts')}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {hosts.map((host) => {
              const probe = probeResults[host.host_alias];
              const isProbing = probingHost === host.host_alias;

              return (
                <div
                  key={host.host_alias}
                  className="p-3.5 rounded-lg border border-border bg-muted/30 hover:bg-muted/50 transition-all space-y-2.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Terminal className="w-4 h-4 text-primary shrink-0" />
                      <span className="font-semibold text-xs text-foreground">
                        {host.host_alias}
                      </span>
                    </div>

                    <button
                      onClick={() => handleProbe(host.host_alias)}
                      disabled={isProbing}
                      className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded bg-background border border-border hover:bg-accent text-foreground transition-colors disabled:opacity-50"
                    >
                      <Activity className={cn('w-3 h-3', isProbing && 'animate-pulse text-amber-500')} />
                      {isProbing ? t('probing') : t('probe')}
                    </button>
                  </div>

                  <div className="text-[11px] font-mono text-muted-foreground space-y-0.5">
                    <div>
                      {host.user}@{host.hostname}:{host.port}
                    </div>
                    {host.identity_file && (
                      <div className="text-[10px] truncate text-muted-foreground/80">
                        Key: {host.identity_file}
                      </div>
                    )}
                  </div>

                  <div className="flex items-center justify-between pt-1 border-t border-border/50 text-[11px]">
                    <div className="flex items-center gap-1">
                      {probe ? (
                        probe.is_reachable ? (
                          <span className="flex items-center gap-1 text-emerald-500">
                            <CheckCircle2 className="w-3.5 h-3.5" />
                            <span>{probe.latency_ms}ms</span>
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 text-rose-500" title={probe.error_message || ''}>
                            <XCircle className="w-3.5 h-3.5" />
                            <span>Offline</span>
                          </span>
                        )
                      ) : (
                        <span className="text-muted-foreground">{t('statusUntested')}</span>
                      )}
                    </div>

                    <button
                      onClick={() => copyPromptHint(host.host_alias)}
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                      title={t('copyPrompt')}
                    >
                      {copiedAlias === host.host_alias ? (
                        <>
                          <Check className="w-3 h-3" />
                          <span>{t('copied')}</span>
                        </>
                      ) : (
                        <>
                          <Copy className="w-3 h-3" />
                          <span>{t('useInPrompt')}</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
