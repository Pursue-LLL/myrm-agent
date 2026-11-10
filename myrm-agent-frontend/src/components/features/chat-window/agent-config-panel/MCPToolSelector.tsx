'use client';

import { useState, useEffect, useCallback, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronDown, Shield, AlertTriangle, Eye, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { Checkbox } from '@/components/primitives/checkbox';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
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
  if (tool.destructiveHint) {
    return 'danger';
  }
  if (!tool.readOnlyHint && !tool.idempotentHint) {
    return 'caution';
  }
  return 'safe';
}

const RISK_CONFIG: Record<RiskLevel, { icon: typeof Shield; className: string; labelKey: string }> = {
  safe: { icon: Shield, className: 'text-green-500', labelKey: 'readOnly' },
  caution: { icon: Eye, className: 'text-yellow-500', labelKey: 'writable' },
  danger: { icon: AlertTriangle, className: 'text-red-500', labelKey: 'destructive' },
};

type ServerToolSelectorProps = Omit<MCPToolSelectorProps, 'isServerEnabled'>;

/** The selector of a server that is selected: what it reads and holds is dropped when the server is switched off. */
const ServerToolSelector = ({ mcpConfig, serverName, selectedTools, onSelectionChange }: ServerToolSelectorProps) => {
  const t = useTranslations('agent.configPanel.mcpTools');
  const [tools, setTools] = useState<MCPToolDetail[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const fetchedRef = useRef(false);
  // The read whose answer is still wanted: null while none runs, and again once the selector is gone, so an answer
  // that arrives then never reaches the parent.
  const activeReadRef = useRef<object | null>(null);
  // What a read needs once its answer arrives; kept current so new objects from the parent do not restart it.
  const latestRef = useRef({ mcpConfig, serverName, selectedTools, onSelectionChange });
  useEffect(() => {
    latestRef.current = { mcpConfig, serverName, selectedTools, onSelectionChange };
  });

  const loadTools = useCallback(async () => {
    if (fetchedRef.current || activeReadRef.current) {
      return;
    }
    const read = {};
    activeReadRef.current = read;
    setLoading(true);
    setLoadError(false);
    const { tools: fetchedTools, error } = await fetchMCPTools(latestRef.current.mcpConfig);
    if (activeReadRef.current !== read) {
      return;
    }
    activeReadRef.current = null;
    setLoading(false);
    if (error) {
      setLoadError(true);
      return;
    }
    setTools(fetchedTools);
    fetchedRef.current = true;

    // A server with destructive tools starts with only the other tools on; the user opts in to the rest.
    const { selectedTools: chosen, serverName: name, onSelectionChange: choose } = latestRef.current;
    if (!chosen && fetchedTools.some((item) => item.destructiveHint)) {
      choose(
        name,
        fetchedTools.filter((item) => !item.destructiveHint).map((item) => item.name),
      );
    }
  }, []);

  useEffect(() => {
    if (expanded) {
      void loadTools();
    }
  }, [expanded, loadTools]);

  useEffect(
    () => () => {
      activeReadRef.current = null;
    },
    [],
  );

  const isAllSelected = !selectedTools;
  const enabledSet = new Set(selectedTools ?? tools.map((item) => item.name));
  // A name the server no longer offers can stay in a saved choice; it is no tool the user can see, so it is not counted.
  const enabledCount = tools.filter((item) => enabledSet.has(item.name)).length;
  const disabledDangerousCount = tools.filter((item) => item.destructiveHint && !enabledSet.has(item.name)).length;

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
      onSelectionChange(serverName, tools.every((item) => current.has(item.name)) ? undefined : Array.from(current));
    }
  };

  const handleSelectAll = () => {
    onSelectionChange(serverName, undefined);
  };

  let filterSummary = '';
  if (tools.length > 0) {
    filterSummary = selectedTools ? `${enabledCount}/${tools.length}` : `${tools.length}`;
  }

  return (
    <div className="mt-1 ml-6 sm:ml-10 mr-1 sm:mr-3">
      <button
        type="button"
        aria-expanded={expanded}
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
              <span className="text-xs text-destructive-text">{t('loadFailed')}</span>
              <button
                type="button"
                onClick={() => void loadTools()}
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
              {disabledDangerousCount > 0 && (
                <div className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg bg-destructive/10 text-[11px] text-destructive-text">
                  <AlertTriangle size={11} />
                  <span>{t('dangerDisabled', { count: disabledDangerousCount })}</span>
                </div>
              )}
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
                    {enabledCount} / {tools.length}
                  </span>
                )}
              </div>

              {tools.map((tool) => {
                const config = RISK_CONFIG[getRiskLevel(tool)];
                const RiskIcon = config.icon;
                const riskLabel = t(config.labelKey);
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
                        <RiskIcon size={12} aria-hidden className={config.className} />
                      </TooltipTrigger>
                      <TooltipContent side="left" className="text-xs max-w-[200px]">
                        <p className="font-medium">{riskLabel}</p>
                        {tool.description && (
                          <p className="text-muted-foreground mt-0.5">{tool.description.slice(0, 120)}</p>
                        )}
                      </TooltipContent>
                    </Tooltip>
                    <span className="sr-only">{riskLabel}</span>
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

/**
 * Per-server MCP tool selector with risk annotations.
 *
 * When `selectedTools` is undefined (no filter), all tools are enabled.
 * Toggling any tool off creates an explicit whitelist of the remaining tools.
 * While the server is not selected nothing is shown or read.
 */
const MCPToolSelector = ({ isServerEnabled, ...selector }: MCPToolSelectorProps) =>
  isServerEnabled ? <ServerToolSelector {...selector} /> : null;

export default MCPToolSelector;
