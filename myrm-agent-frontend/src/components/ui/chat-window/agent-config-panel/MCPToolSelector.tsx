'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, Shield, AlertTriangle, Eye, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Checkbox } from '@/components/ui/checkbox';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { MCPServiceConfig } from '@/store/config/types';
import { fetchMCPTools, type MCPToolDetail } from '@/services/llm-config';

interface MCPToolSelectorProps {
  mcpConfig: MCPServiceConfig;
  serverName: string;
  selectedTools: string[] | undefined;
  onSelectionChange: (serverName: string, tools: string[] | undefined) => void;
  isServerEnabled: boolean;
}

type RiskLevel = 'safe' | 'caution' | 'danger';

function getRiskLevel(tool: MCPToolDetail): RiskLevel {
  if (tool.destructiveHint) return 'danger';
  if (!tool.readOnlyHint && !tool.idempotentHint) return 'caution';
  return 'safe';
}

const RISK_CONFIG: Record<RiskLevel, { icon: typeof Shield; className: string; labelKey: string }> = {
  safe: { icon: Shield, className: 'text-green-500', labelKey: 'readOnly' },
  caution: { icon: Eye, className: 'text-yellow-500', labelKey: 'writable' },
  danger: { icon: AlertTriangle, className: 'text-red-500', labelKey: 'destructive' },
};

/**
 * Per-server MCP tool selector with risk annotations.
 *
 * When `selectedTools` is undefined (no filter), all tools are enabled.
 * Toggling any tool off creates an explicit whitelist of the remaining tools.
 */
const MCPToolSelector = ({
  mcpConfig,
  serverName,
  selectedTools,
  onSelectionChange,
  isServerEnabled,
}: MCPToolSelectorProps) => {
  const t = useTranslations('agent.configPanel.mcpTools');
  const [tools, setTools] = useState<MCPToolDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fetchedRef = useRef(false);
  const selectedToolsRef = useRef(selectedTools);
  selectedToolsRef.current = selectedTools;

  const loadTools = useCallback(async () => {
    if (fetchedRef.current || !isServerEnabled) return;
    setLoading(true);
    setLoadError(false);
    try {
      const { tools: fetchedTools, error } = await fetchMCPTools(mcpConfig);
      if (error) {
        setLoadError(true);
        return;
      }
      setTools(fetchedTools);
      fetchedRef.current = true;

      if (!selectedToolsRef.current && fetchedTools.length > 0) {
        const hasDangerous = fetchedTools.some((item) => item.destructiveHint);
        if (hasDangerous) {
          const safeDefaults = fetchedTools.filter((item) => !item.destructiveHint).map((item) => item.name);
          onSelectionChange(serverName, safeDefaults);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [mcpConfig, isServerEnabled, onSelectionChange, serverName]);

  const handleRetry = useCallback(() => {
    fetchedRef.current = false;
    setLoadError(false);
    loadTools();
  }, [loadTools]);

  useEffect(() => {
    if (expanded && !fetchedRef.current) {
      loadTools();
    }
  }, [expanded, loadTools]);

  useEffect(() => {
    if (!isServerEnabled) {
      fetchedRef.current = false;
      setTools([]);
      setExpanded(false);
      setLoadError(false);
    }
  }, [isServerEnabled]);

  const isAllSelected = !selectedTools;
  const enabledSet = new Set(selectedTools ?? tools.map((item) => item.name));

  const handleToggleTool = (toolName: string) => {
    if (isAllSelected) {
      const remaining = tools.filter((item) => item.name !== toolName).map((item) => item.name);
      onSelectionChange(serverName, remaining);
    } else {
      const current = new Set(selectedTools);
      if (current.has(toolName)) {
        current.delete(toolName);
      } else {
        current.add(toolName);
      }
      const newSelection = Array.from(current);
      onSelectionChange(serverName, newSelection.length === tools.length ? undefined : newSelection);
    }
  };

  const handleSelectAll = () => {
    onSelectionChange(serverName, undefined);
  };

  if (!isServerEnabled) return null;

  const filterSummary =
    selectedTools && tools.length > 0
      ? `${selectedTools.length}/${tools.length}`
      : tools.length > 0
        ? `${tools.length}`
        : '';

  return (
    <div className="mt-1 ml-6 sm:ml-10 mr-1 sm:mr-3">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className={cn(
          'flex items-center gap-1.5 text-xs text-muted-foreground/70 hover:text-muted-foreground transition-colors',
          expanded && 'text-muted-foreground',
        )}
      >
        <ChevronDown size={12} className={cn('transition-transform', expanded && 'rotate-180')} />
        <span>{t('toolFilter')}</span>
        {filterSummary && <span className="text-[10px] bg-muted/60 px-1.5 py-0.5 rounded-md">{filterSummary}</span>}
      </button>

      {expanded && (
        <div className="mt-2 space-y-1 pb-1">
          {loading && <div className="text-xs text-muted-foreground/60 py-2 pl-1">{t('loading')}</div>}

          {!loading && loadError && (
            <div className="flex items-center gap-2 py-2 pl-1">
              <span className="text-xs text-destructive/80">{t('loadFailed')}</span>
              <button
                type="button"
                onClick={handleRetry}
                className="flex items-center gap-1 text-[11px] text-primary/70 hover:text-primary transition-colors"
              >
                <RefreshCw size={10} />
                <span>{t('retry')}</span>
              </button>
            </div>
          )}

          {!loading && !loadError && tools.length === 0 && (
            <div className="text-xs text-muted-foreground/60 py-2 pl-1">{t('noTools')}</div>
          )}

          {!loading && tools.length > 0 && (
            <>
              {selectedTools &&
                (() => {
                  const disabledDangerous = tools.filter((item) => item.destructiveHint && !enabledSet.has(item.name));
                  if (disabledDangerous.length === 0) return null;
                  return (
                    <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-destructive/10 text-[11px] text-destructive/80">
                      <AlertTriangle size={11} />
                      <span>{t('dangerDisabled', { count: disabledDangerous.length })}</span>
                    </div>
                  );
                })()}
              <div className="flex items-center justify-between mb-1.5 px-1">
                <button
                  type="button"
                  onClick={handleSelectAll}
                  className="text-[11px] text-primary/70 hover:text-primary transition-colors"
                >
                  {t('selectAll')}
                </button>
                {selectedTools && (
                  <span className="text-[10px] text-muted-foreground/60">
                    {selectedTools.length} / {tools.length}
                  </span>
                )}
              </div>

              {tools.map((tool) => {
                const risk = getRiskLevel(tool);
                const config = RISK_CONFIG[risk];
                const RiskIcon = config.icon;
                const checked = enabledSet.has(tool.name);

                return (
                  <label
                    key={tool.name}
                    className={cn(
                      'flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer text-xs',
                      'hover:bg-muted/40 transition-colors',
                      !checked && 'opacity-50',
                    )}
                  >
                    <Checkbox
                      checked={checked}
                      onCheckedChange={() => handleToggleTool(tool.name)}
                      className="h-3.5 w-3.5"
                    />
                    <span className="flex-1 truncate">{tool.name}</span>
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <RiskIcon size={12} className={config.className} />
                      </TooltipTrigger>
                      <TooltipContent side="left" className="text-xs max-w-[200px]">
                        <p className="font-medium">{t(config.labelKey)}</p>
                        {tool.description && (
                          <p className="text-muted-foreground mt-0.5">{tool.description.slice(0, 120)}</p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  </label>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
};

export default MCPToolSelector;
