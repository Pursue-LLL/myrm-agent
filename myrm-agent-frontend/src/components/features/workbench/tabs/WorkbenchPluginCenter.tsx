'use client';

/**
 * [INPUT]
 * - fetchWorkbenchPlugins, probePluginHealth from @/services/workbench
 * - useTranslations from next-intl (namespace: 'workbench.plugins')
 *
 * [OUTPUT]
 * - WorkbenchPluginCenter: Plugin lifecycle, health probes & repair hub
 *
 * [POS]
 * Auxiliary Workbench Plugin Center tab component.
 * Single file < 260 lines. Zero `any` types. Zero native emoji.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import {
  Boxes,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ExternalLink,
  Activity,
  Wrench,
  RefreshCw,
  Loader2,
} from 'lucide-react';
import {
  fetchWorkbenchPlugins,
  probePluginHealth,
  type PluginItem,
  type PluginProbeResponse,
} from '@/services/workbench';

export function WorkbenchPluginCenter() {
  const t = useTranslations('workbench.plugins');
  const [plugins, setPlugins] = useState<PluginItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [probingId, setProbingId] = useState<string | null>(null);
  const [probeResult, setProbeResult] = useState<PluginProbeResponse | null>(null);

  const loadPlugins = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchWorkbenchPlugins();
      setPlugins(data);
    } catch {
      // Fallback
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPlugins();
  }, [loadPlugins]);

  const handleProbe = async (pluginId: string) => {
    setProbingId(pluginId);
    setProbeResult(null);
    try {
      const res = await probePluginHealth(pluginId);
      setProbeResult(res);
      // Update local plugin status
      setPlugins((prev) =>
        prev.map((p) =>
          p.plugin_id === pluginId
            ? { ...p, status: res.status, last_probed_at: new Date().toISOString() }
            : p,
        ),
      );
    } catch {
      // Fallback
    } finally {
      setProbingId(null);
    }
  };

  const handleRepair = (pluginId: string) => {
    // Simulated instant repair
    setPlugins((prev) =>
      prev.map((p) =>
        p.plugin_id === pluginId ? { ...p, status: 'healthy' } : p,
      ),
    );
  };

  return (
    <div className="flex flex-col h-full overflow-hidden text-foreground bg-background">
      {/* Header */}
      <div className="p-2 border-b border-border/60 flex items-center justify-between gap-2 bg-card/60 text-xs">
        <div className="flex items-center gap-2">
          <Boxes className="w-4 h-4 text-primary" />
          <span className="font-semibold">{t('headerTitle')}</span>
          <span className="text-[10px] text-muted-foreground font-mono">
            {plugins.length} {t('installedCount')}
          </span>
        </div>

        <button
          type="button"
          onClick={() => void loadPlugins()}
          disabled={isLoading}
          aria-label={t('refreshAction')}
          className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
        {probeResult && (
          <div className="p-3 rounded-xl bg-card border border-primary/40 shadow-sm flex items-start justify-between gap-2 text-xs">
            <div className="flex flex-col gap-1">
              <div className="flex items-center gap-1.5 font-bold text-primary">
                <Activity className="w-3.5 h-3.5" />
                <span>{t('probeSuccessTitle', { id: probeResult.plugin_id })}</span>
              </div>
              <p className="text-muted-foreground text-[11px]">{probeResult.message}</p>
              <div className="flex items-center gap-3 text-[10px] font-mono text-muted-foreground pt-1">
                <span>Latency: {probeResult.latency_ms}ms</span>
                <span>Status: {probeResult.status}</span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setProbeResult(null)}
              className="text-xs text-muted-foreground hover:text-foreground p-1"
            >
              ✕
            </button>
          </div>
        )}

        {plugins.length === 0 && !isLoading ? (
          <div className="text-center py-12 text-xs text-muted-foreground">
            {t('emptyPlugins')}
          </div>
        ) : (
          plugins.map((plugin) => {
            const isProbingThis = probingId === plugin.plugin_id;
            return (
              <div
                key={plugin.plugin_id}
                className="p-3.5 rounded-2xl bg-card border border-border/70 hover:border-border shadow-xs flex flex-col gap-2.5 transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div className="w-8 h-8 rounded-xl bg-primary/10 text-primary flex items-center justify-center font-bold">
                      <Boxes className="w-4 h-4" />
                    </div>
                    <div>
                      <h4 className="text-xs font-semibold flex items-center gap-1.5">
                        <span>{plugin.name}</span>
                        <span className="text-[10px] font-mono text-muted-foreground font-normal">
                          v{plugin.version}
                        </span>
                      </h4>
                      <p className="text-[11px] text-muted-foreground">{plugin.description}</p>
                    </div>
                  </div>

                  {/* Status Badge */}
                  <span
                    className={`flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wider ${
                      plugin.status === 'healthy'
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                        : plugin.status === 'degraded'
                        ? 'bg-amber-500/15 text-amber-600 dark:text-amber-400'
                        : 'bg-rose-500/15 text-rose-600 dark:text-rose-400'
                    }`}
                  >
                    {plugin.status === 'healthy' ? (
                      <CheckCircle2 className="w-3 h-3" />
                    ) : plugin.status === 'degraded' ? (
                      <AlertTriangle className="w-3 h-3" />
                    ) : (
                      <XCircle className="w-3 h-3" />
                    )}
                    <span>{plugin.status}</span>
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs pt-1 border-t border-border/40">
                  <span className="text-[10px] font-mono text-muted-foreground">
                    by {plugin.author}
                  </span>

                  <div className="flex items-center gap-1.5">
                    {plugin.github_repo && (
                      <a
                        href={plugin.github_repo}
                        target="_blank"
                        rel="noreferrer"
                        className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
                        title={t('viewGithub')}
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </a>
                    )}

                    {plugin.status !== 'healthy' && (
                      <button
                        type="button"
                        onClick={() => handleRepair(plugin.plugin_id)}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 text-[11px] font-medium transition-colors"
                      >
                        <Wrench className="w-3 h-3" />
                        <span>{t('repairAction')}</span>
                      </button>
                    )}

                    <button
                      type="button"
                      onClick={() => void handleProbe(plugin.plugin_id)}
                      disabled={isProbingThis}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-lg bg-muted/80 hover:bg-muted text-foreground text-[11px] font-medium transition-colors disabled:opacity-50"
                    >
                      {isProbingThis ? (
                        <Loader2 className="w-3 h-3 animate-spin text-primary" />
                      ) : (
                        <Activity className="w-3 h-3 text-primary" />
                      )}
                      <span>{t('probeAction')}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
