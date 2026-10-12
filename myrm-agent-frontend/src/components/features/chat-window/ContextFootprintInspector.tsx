'use client';

/**
 * [INPUT]
 * - store/useConfigStore::mcpConfigs, toggleMCPConfig, systemInstructions (POS: MCP and system instruction state)
 * - store/useChatStore::agentConfig (POS: Active agent configuration)
 * - next-intl::useTranslations (POS: Internationalization)
 * - lucide-react::Cpu, Sparkles, Layers, Settings2, X, Power (POS: Status & category icons)
 *
 * [OUTPUT]
 * - ContextFootprintInspector: initial baseline context token footprint inspector & idle MCP switcher modal.
 *
 * [POS]
 * Claude Code /context command parity inspector. Reveals pre-conversation baseline token footprint
 * across System Prompt, Persona, Workspace Rules, and MCP Tool Schemas with an instant idle MCP switcher.
 */

import React, { useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { Cpu, Sparkles, Layers, Settings2, X, Power, CheckCircle2 } from 'lucide-react';
import useConfigStore from '@/store/useConfigStore';
import useChatStore from '@/store/useChatStore';
import type { MCPServiceConfig } from '@/store/config/types';

export interface ContextFootprintInspectorProps {
  open: boolean;
  onClose: () => void;
  className?: string;
}

export function formatTokenNumber(tokens: number): string {
  if (tokens >= 1000) {
    const val = tokens / 1000;
    return `${val % 1 === 0 ? val.toFixed(0) : val.toFixed(1)}k`;
  }
  return tokens.toString();
}

export default function ContextFootprintInspector({
  open,
  onClose,
  className = '',
}: ContextFootprintInspectorProps) {
  const t = useTranslations('chat.contextFootprint');
  const mcpConfigs = useConfigStore((s) => s.mcpConfigs);
  const toggleMCPConfig = useConfigStore((s) => s.toggleMCPConfig);
  const systemInstructions = useConfigStore((s) => s.systemInstructions);
  const agentConfig = useChatStore((s) => s.agentConfig);

  const baselineBreakdown = useMemo(() => {
    const systemPromptTokens = 800 + Math.round((systemInstructions?.length ?? 0) / 3.5);
    const personaTokens = 500 + Math.round((agentConfig?.agentDescription?.length ?? 0) / 3.5);
    const workspaceRulesTokens = 600;

    const enabledMcpList = mcpConfigs.filter((cfg: MCPServiceConfig) => cfg.enabled !== false);
    // Average MCP service exposes ~8 tools, with ~350 tokens schema overhead per tool
    const mcpToolsTokens = enabledMcpList.length * 8 * 350;
    const skillsToolsTokens = 1200;

    const totalBaselineTokens =
      systemPromptTokens + personaTokens + workspaceRulesTokens + mcpToolsTokens + skillsToolsTokens;

    return {
      systemPromptTokens,
      personaTokens,
      workspaceRulesTokens,
      mcpToolsTokens,
      skillsToolsTokens,
      totalBaselineTokens,
      enabledMcpCount: enabledMcpList.length,
      totalMcpCount: mcpConfigs.length,
    };
  }, [systemInstructions, agentConfig, mcpConfigs]);

  if (!open) {
    return null;
  }

  const { totalBaselineTokens, mcpToolsTokens } = baselineBreakdown;
  const isHeavyBaseline = totalBaselineTokens > 6000;
  const isLightBaseline = totalBaselineTokens <= 3500;

  return (
    <dialog
      open
      aria-modal="true"
      aria-labelledby="context-footprint-title"
      data-testid="context-footprint-inspector"
      className={`fixed inset-0 z-50 flex items-center justify-center p-4 bg-background/80 backdrop-blur-xs border-none m-0 max-w-none max-h-none w-full h-full ${className}`}
    >
      <div className="relative w-full max-w-lg p-5 rounded-xl border border-border/80 bg-card shadow-2xl text-card-foreground animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between pb-3 border-b border-border/50">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-primary" />
            <h2 id="context-footprint-title" className="text-base font-semibold">
              {t('title')}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label={t('close')}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <p className="text-xs text-muted-foreground mt-2 leading-relaxed">{t('subtitle')}</p>

        {/* Total Baseline Badge */}
        <div className="mt-3.5 p-3 rounded-lg bg-muted/30 border border-border/40 flex items-center justify-between">
          <div className="flex flex-col">
            <span className="text-[11px] font-medium text-muted-foreground">{t('totalBaseline')}</span>
            <span className="text-lg font-bold tracking-tight text-foreground tabular-nums">
              ~{formatTokenNumber(totalBaselineTokens)} tokens
            </span>
          </div>
          <span
            className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${
              isLightBaseline
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25'
                : isHeavyBaseline
                  ? 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/25'
                  : 'bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/25'
            }`}
          >
            {isLightBaseline ? 'Featherlight' : isHeavyBaseline ? 'Heavy Baseline' : 'Moderate'}
          </span>
        </div>

        {/* 5-layer Breakdown Rows */}
        <div className="mt-3.5 space-y-2 text-xs">
          <div className="flex items-center justify-between py-1 border-b border-border/30 text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Layers className="w-3.5 h-3.5 text-indigo-500" />
              {t('systemPrompt')}
            </span>
            <span className="font-mono text-foreground">~{formatTokenNumber(baselineBreakdown.systemPromptTokens)} t</span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border/30 text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-purple-500" />
              {t('persona')}
            </span>
            <span className="font-mono text-foreground">~{formatTokenNumber(baselineBreakdown.personaTokens)} t</span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border/30 text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Settings2 className="w-3.5 h-3.5 text-cyan-500" />
              {t('workspaceRules')}
            </span>
            <span className="font-mono text-foreground">~{formatTokenNumber(baselineBreakdown.workspaceRulesTokens)} t</span>
          </div>
          <div className="flex items-center justify-between py-1 border-b border-border/30 text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <Cpu className="w-3.5 h-3.5 text-amber-500" />
              {t('mcpTools')}
            </span>
            <span className="font-mono text-foreground font-semibold text-amber-600 dark:text-amber-400">
              ~{formatTokenNumber(mcpToolsTokens)} t
            </span>
          </div>
          <div className="flex items-center justify-between py-1 text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
              {t('skillsTools')}
            </span>
            <span className="font-mono text-foreground">~{formatTokenNumber(baselineBreakdown.skillsToolsTokens)} t</span>
          </div>
        </div>

        {/* Idle MCP Switcher Section */}
        <div className="mt-4 pt-3.5 border-t border-border/60">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1.5">
              <Power className="w-4 h-4 text-primary" />
              <h3 className="text-xs font-semibold text-foreground">{t('mcpSwitcherTitle')}</h3>
            </div>
            <span className="text-[10px] text-muted-foreground tabular-nums">
              {baselineBreakdown.enabledMcpCount} / {baselineBreakdown.totalMcpCount} {t('enabled')}
            </span>
          </div>
          <p className="text-[11px] text-muted-foreground leading-snug mb-2.5">{t('mcpSwitcherDesc')}</p>

          <div className="max-h-36 overflow-y-auto space-y-1.5 pr-0.5">
            {mcpConfigs.length === 0 ? (
              <p className="text-[11px] text-muted-foreground text-center py-3">{t('noMcpServers')}</p>
            ) : (
              mcpConfigs.map((cfg: MCPServiceConfig, index: number) => {
                const isEnabled = cfg.enabled !== false;
                return (
                  <div
                    key={cfg.name || index}
                    data-testid={`mcp-server-item-${index}`}
                    className="flex items-center justify-between p-2 rounded-md bg-muted/20 hover:bg-muted/40 border border-border/30 transition-colors"
                  >
                    <div className="flex flex-col min-w-0 pr-2">
                      <span className="text-xs font-medium text-foreground truncate">{cfg.name}</span>
                      <span className="text-[10px] text-muted-foreground truncate">{cfg.url || cfg.command || cfg.type}</span>
                    </div>
                    <button
                      type="button"
                      data-testid={`mcp-toggle-button-${index}`}
                      onClick={() => toggleMCPConfig(index)}
                      className={`px-2 py-0.5 text-[10px] font-medium rounded-full border transition-colors ${
                        isEnabled
                          ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                          : 'bg-muted text-muted-foreground border-border/40'
                      }`}
                    >
                      {isEnabled ? t('enabled') : t('disabled')}
                    </button>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>
    </dialog>
  );
}
