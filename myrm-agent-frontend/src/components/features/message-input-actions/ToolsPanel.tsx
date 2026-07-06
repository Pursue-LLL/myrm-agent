'use client';

import { useState, useMemo } from 'react';
import { Wrench, Search, ChevronDown, ChevronRight } from 'lucide-react';
import { useLocale, useTranslations } from 'next-intl';
import useToolsSnapshotStore from '@/store/useToolsSnapshotStore';
import { resolveToolSnapshotDisplayName } from '@/store/chat/types/builtinTools';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/primitives/popover';
import { Badge } from '@/components/primitives/badge';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';
import type { ToolSnapshotItem } from '@/store/chat/types';

type GroupedTools = Record<string, ToolSnapshotItem[]>;

function groupBySource(tools: ToolSnapshotItem[]): GroupedTools {
  const groups: GroupedTools = {};
  for (const tool of tools) {
    const key = tool.provider ?? tool.source;
    if (!groups[key]) groups[key] = [];
    groups[key].push(tool);
  }
  return groups;
}

function sourceLabel(key: string): string {
  if (key.startsWith('skill:')) return key.replace('skill:', '');
  if (key.startsWith('mcp:')) return key.replace('mcp:', '');
  const labels: Record<string, string> = {
    builtin: 'Built-in',
    user: 'User',
    middleware: 'Middleware',
  };
  return labels[key] ?? key;
}

function sourceBadgeVariant(source: string): 'default' | 'secondary' | 'outline' {
  if (source === 'skill' || source.startsWith('skill:')) return 'default';
  if (source === 'mcp' || source.startsWith('mcp:')) return 'secondary';
  return 'outline';
}

function ToolItem({ tool }: { tool: ToolSnapshotItem }) {
  const [expanded, setExpanded] = useState(false);
  const t = useTranslations('chat.toolsPanel');
  const locale = useLocale();
  const uiLocale = locale.startsWith('zh') ? 'zh' : 'en';
  const knownName =
    tool.name === 'conversation_search' ? t('knownTools.conversationSearch.name') : undefined;
  const displayName = resolveToolSnapshotDisplayName(tool, uiLocale, knownName);
  const displaySummary =
    tool.name === 'conversation_search' ? t('knownTools.conversationSearch.summary') : tool.summary;

  return (
    <div className="border-b border-border/50 last:border-b-0">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-muted/50 transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-muted-foreground flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-muted-foreground flex-shrink-0" />
        )}
        <span className="text-sm font-medium truncate flex-1">{displayName}</span>
        <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-4 flex-shrink-0">
          {tool.layer}
        </Badge>
      </button>
      {expanded && (
        <div className="px-3 pb-2 pl-8 space-y-1.5">
          <p className="text-xs text-muted-foreground leading-relaxed">{displaySummary}</p>
          {tool.parameters_schema && Object.keys(tool.parameters_schema).length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer text-muted-foreground/70 hover:text-muted-foreground">
                {t('parameters')}
              </summary>
              <pre className="mt-1 p-2 bg-muted/50 rounded text-[10px] overflow-x-auto max-h-32">
                {JSON.stringify(tool.parameters_schema, null, 2)}
              </pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

function ToolGroup({ groupKey, tools }: { groupKey: string; tools: ToolSnapshotItem[] }) {
  const [collapsed, setCollapsed] = useState(false);
  const source = tools[0]?.source ?? 'builtin';

  return (
    <div className="mb-2 last:mb-0">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-muted/30 transition-colors"
      >
        {collapsed ? (
          <ChevronRight size={12} className="text-muted-foreground" />
        ) : (
          <ChevronDown size={12} className="text-muted-foreground" />
        )}
        <Badge variant={sourceBadgeVariant(source)} className="text-[10px] px-1.5 py-0 h-4">
          {sourceLabel(groupKey)}
        </Badge>
        <span className="text-[10px] text-muted-foreground/60 ml-auto">{tools.length}</span>
      </button>
      {!collapsed && (
        <div className="ml-1 border-l border-border/30">
          {tools.map((tool) => (
            <ToolItem key={tool.name} tool={tool} />
          ))}
        </div>
      )}
    </div>
  );
}

const ToolsPanel = () => {
  const t = useTranslations('chat.toolsPanel');
  const locale = useLocale();
  const tools = useToolsSnapshotStore((s) => s.tools);
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState('');

  const filtered = useMemo(() => {
    if (!search.trim()) return tools;
    const q = search.toLowerCase();
    return tools.filter((item) => {
      const uiLocale = locale.startsWith('zh') ? 'zh' : 'en';
      const knownName =
        item.name === 'conversation_search' ? t('knownTools.conversationSearch.name') : undefined;
      const label = resolveToolSnapshotDisplayName(item, uiLocale, knownName);
      return (
        label.toLowerCase().includes(q) ||
        item.name.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q) ||
        (item.provider?.toLowerCase().includes(q) ?? false)
      );
    });
  }, [tools, search, locale, t]);

  const grouped = useMemo(() => groupBySource(filtered), [filtered]);
  const sortedKeys = useMemo(
    () =>
      Object.keys(grouped).sort((a, b) => {
        const order: Record<string, number> = { builtin: 0, user: 1, middleware: 2 };
        const oa = order[a] ?? (a.startsWith('skill:') ? 3 : 4);
        const ob = order[b] ?? (b.startsWith('skill:') ? 3 : 4);
        return oa - ob || a.localeCompare(b);
      }),
    [grouped],
  );

  if (tools.length === 0) return null;

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <TooltipProvider delayDuration={300}>
        <Tooltip>
          <TooltipTrigger asChild>
            <PopoverTrigger asChild>
              <button
                type="button"
                className={cn(
                  'p-1.5 rounded-full transition-all duration-200',
                  open
                    ? 'text-primary hover:text-primary/80'
                    : 'text-muted-foreground/40 hover:text-muted-foreground/60',
                )}
              >
                <Wrench size={16} />
              </button>
            </PopoverTrigger>
          </TooltipTrigger>
          <TooltipContent side="top" className="text-xs">
            {t('title')} ({tools.length})
          </TooltipContent>
        </Tooltip>
      </TooltipProvider>

      <PopoverContent side="top" align="start" className="w-80 sm:w-96 p-0 max-h-[60vh] flex flex-col">
        {/* Header */}
        <div className="px-3 py-2 border-b border-border flex items-center justify-between">
          <span className="text-sm font-medium">
            {t('title')}
            <span className="text-muted-foreground/60 ml-1.5 text-xs">({tools.length})</span>
          </span>
        </div>

        {/* Search */}
        <div className="px-3 py-2 border-b border-border/50">
          <div className="relative">
            <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted-foreground/50" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('searchPlaceholder')}
              className="w-full pl-7 pr-2 py-1.5 text-xs bg-muted/30 border border-border/50 rounded-full focus:outline-none focus:ring-1 focus:ring-primary/30 placeholder:text-muted-foreground/40"
            />
          </div>
        </div>

        {/* Tool list */}
        <div className="overflow-y-auto flex-1 py-1">
          {sortedKeys.length === 0 ? (
            <p className="text-xs text-muted-foreground/50 text-center py-4">{t('noResults')}</p>
          ) : (
            sortedKeys.map((key) => <ToolGroup key={key} groupKey={key} tools={grouped[key]} />)
          )}
        </div>
      </PopoverContent>
    </Popover>
  );
};

export default ToolsPanel;
