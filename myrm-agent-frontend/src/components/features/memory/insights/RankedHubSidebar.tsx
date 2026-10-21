'use client';

/**
 * [INPUT]
 * @/services/memory/commandCenter::MemoryCommandGraphHubItem
 *
 * [OUTPUT]
 * RankedHubSidebar: Ranked core claims and conflict hotspots sidebar for Knowledge Graph dual-view.
 *
 * [POS]
 * 图谱双重视图之核心主张与冲突焦点侧栏。解决力导向图无序游移、难以提炼关键信念的痛点。
 */

import { memo, useState } from 'react';
import { useTranslations } from 'next-intl';
import { AlertTriangle, ChevronRight, Compass, ShieldAlert, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { MemoryCommandGraphHubItem } from '@/services/memory/commandCenter';

interface RankedHubSidebarProps {
  hubs: MemoryCommandGraphHubItem[];
  selectedHubId?: string | null;
  hoveredHubId?: string | null;
  onSelectHub: (hub: MemoryCommandGraphHubItem) => void;
  onHoverHub: (hubId: string | null) => void;
  className?: string;
}

export const RankedHubSidebar = memo<RankedHubSidebarProps>(
  ({ hubs, selectedHubId, hoveredHubId, onSelectHub, onHoverHub, className }) => {
    const t = useTranslations('memory');
    const [activeTab, setActiveTab] = useState<'all' | 'grounded' | 'conflicted'>('all');

    const filteredHubs = hubs.filter((hub) => {
      if (activeTab === 'grounded') {
        return hub.supported_count > 0 && !hub.has_conflict;
      }
      if (activeTab === 'conflicted') {
        return hub.has_conflict;
      }
      return true;
    });

    const conflictCount = hubs.filter((h) => h.has_conflict).length;

    return (
      <aside
        aria-label="Ranked hub sidebar"
        className={cn(
          'flex flex-col border-l border-border/50 bg-background/95 backdrop-blur-sm select-none',
          className,
        )}
      >
        <div className="flex items-center justify-between border-b border-border/40 px-3 py-2">
          <div className="flex items-center gap-1.5">
            <Compass className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-semibold text-foreground">{t('commandCenter.graph.rankedHubsTitle')}</span>
          </div>
          <span className="rounded-full bg-accent/60 px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {hubs.length}
          </span>
        </div>

        <div className="flex border-b border-border/40 p-1 bg-accent/20 text-[11px]">
          <button
            type="button"
            onClick={() => setActiveTab('all')}
            className={cn(
              'flex-1 rounded px-2 py-1 text-center font-medium transition-colors',
              activeTab === 'all'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t('commandCenter.graph.tabAll')}
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('grounded')}
            className={cn(
              'flex-1 rounded px-2 py-1 text-center font-medium transition-colors',
              activeTab === 'grounded'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <span className="inline-flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-emerald-500" />
              {t('commandCenter.graph.tabGrounded')}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('conflicted')}
            className={cn(
              'flex-1 rounded px-2 py-1 text-center font-medium transition-colors relative',
              activeTab === 'conflicted'
                ? 'bg-background text-foreground shadow-xs'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <span className="inline-flex items-center gap-1">
              <AlertTriangle
                className={cn('h-3 w-3', conflictCount > 0 ? 'text-amber-500' : 'text-muted-foreground')}
              />
              {t('commandCenter.graph.tabConflicted')}
            </span>
            {conflictCount > 0 && <span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-amber-500" />}
          </button>
        </div>

        <div className="flex-1 overflow-y-auto divide-y divide-border/30 p-1">
          {filteredHubs.length === 0 ? (
            <div className="p-4 text-center text-xs text-muted-foreground">{t('commandCenter.graph.noRankedHubs')}</div>
          ) : (
            filteredHubs.map((hub, idx) => {
              const isSelected = selectedHubId === hub.id;
              const isHovered = hoveredHubId === hub.id;

              return (
                <button
                  key={hub.id}
                  type="button"
                  onClick={() => onSelectHub(hub)}
                  onMouseEnter={() => onHoverHub(hub.id)}
                  onMouseLeave={() => onHoverHub(null)}
                  className={cn(
                    'group flex w-full flex-col gap-1 rounded-md p-2 text-left transition-all',
                    isSelected
                      ? 'bg-primary/10 border border-primary/30'
                      : isHovered
                        ? 'bg-accent/40'
                        : 'hover:bg-accent/20',
                  )}
                >
                  <div className="flex items-center justify-between gap-1.5">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-secondary text-[9px] font-semibold text-muted-foreground">
                        {idx + 1}
                      </span>
                      <span
                        className={cn(
                          'truncate text-xs font-medium',
                          hub.has_conflict ? 'text-amber-600 dark:text-amber-400 font-semibold' : 'text-foreground',
                        )}
                      >
                        {hub.snippet}
                      </span>
                    </div>
                    <ChevronRight className="h-3 w-3 shrink-0 text-muted-foreground/60 transition-transform group-hover:translate-x-0.5" />
                  </div>

                  <div className="flex items-center gap-2 pl-5.5 text-[10px] text-muted-foreground">
                    <span className="inline-flex items-center gap-0.5">
                      <span className="font-semibold text-foreground">{hub.degree}</span>{' '}
                      {t('commandCenter.graph.degreeConnections')}
                    </span>
                    {hub.supported_count > 0 && (
                      <span className="text-emerald-600 dark:text-emerald-400">
                        +{hub.supported_count} {t('commandCenter.graph.supportedEvidence')}
                      </span>
                    )}
                    {hub.has_conflict && (
                      <span className="inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400 font-medium">
                        <ShieldAlert className="h-2.5 w-2.5" />
                        {t('commandCenter.graph.conflictFlag')}
                      </span>
                    )}
                  </div>
                </button>
              );
            })
          )}
        </div>
      </aside>
    );
  },
);

RankedHubSidebar.displayName = 'RankedHubSidebar';
