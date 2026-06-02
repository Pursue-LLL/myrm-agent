'use client';

import React, { useState, useCallback } from 'react';
import { Maximize01Icon, Minimize01Icon } from 'hugeicons-react';
import { useTranslations } from 'next-intl';
import type { LegendItem } from './mermaid-theme';

interface MermaidLegendPanelProps {
  legends: LegendItem[];
  activeLegends: Set<string>;
  onToggleLegend: (className: string) => void;
}

const MermaidLegendPanel: React.FC<MermaidLegendPanelProps> = ({ legends, activeLegends, onToggleLegend }) => {
  const t = useTranslations('mermaidChart');
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleToggleCollapse = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      setIsCollapsed(!isCollapsed);
    },
    [isCollapsed],
  );

  if (legends.length === 0) return null;

  return (
    <div className="absolute bottom-4 left-4 z-20 flex flex-col items-start max-w-[200px] bg-background/95 dark:bg-background/95 border border-border rounded-xl shadow-lg backdrop-blur-md overflow-hidden transition-all duration-300">
      <div
        className="flex items-center justify-between w-full px-3 py-2 cursor-pointer bg-muted/30 hover:bg-muted/50 transition-colors"
        onClick={handleToggleCollapse}
      >
        <span className="text-xs font-semibold text-foreground/80 tracking-wide">{t('legend') || '图例 (Legend)'}</span>
        <div className="text-muted-foreground">
          {isCollapsed ? <Maximize01Icon size={14} /> : <Minimize01Icon size={14} />}
        </div>
      </div>

      {!isCollapsed && (
        <div className="flex flex-col w-full p-2 space-y-1.5 max-h-[200px] overflow-y-auto scrollbar-hide">
          {legends.map((legend) => {
            const isActive = activeLegends.size === 0 || activeLegends.has(legend.className);
            return (
              <div
                key={legend.className}
                onClick={(e) => {
                  e.stopPropagation();
                  onToggleLegend(legend.className);
                }}
                className={`flex items-center space-x-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all duration-200 ${
                  isActive
                    ? 'bg-primary/10 text-primary dark:bg-primary/20 dark:text-primary-foreground'
                    : 'bg-transparent text-muted-foreground hover:bg-muted'
                }`}
              >
                <div
                  className="w-3 h-3 rounded-full border border-border/50 flex-shrink-0"
                  style={{ backgroundColor: legend.color || 'var(--primary)' }}
                />
                <span className="text-xs font-medium truncate" title={legend.label}>
                  {legend.label}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default MermaidLegendPanel;
