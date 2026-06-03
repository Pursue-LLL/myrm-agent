'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { X, MoreHorizontal } from 'lucide-react';
import { Artifact, ArtifactType } from '@/store/chat/types';
import { getArtifactIcon } from '../artifactUtils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';

interface OpenArtifactTab {
  artifact: Artifact;
  isGenerating: boolean;
}

interface PortalTabsProps {
  tabs: OpenArtifactTab[];
  activeIndex: number;
  onSwitchTab: (index: number) => void;
  onCloseTab: (index: number) => void;
  onCloseOtherTabs: (index: number) => void;
  onCloseAllTabs: () => void;
  labels: {
    close: string;
    closeOthers: string;
    closeAll: string;
    generating: string;
  };
}

/** Portal 标签页栏 */
const PortalTabs: React.FC<PortalTabsProps> = ({
  tabs,
  activeIndex,
  onSwitchTab,
  onCloseTab,
  onCloseOtherTabs,
  onCloseAllTabs,
  labels,
}) => {
  if (tabs.length <= 1) {
    return null;
  }

  return (
    <div className="flex-shrink-0 border-b border-border bg-muted/30">
      <div className="flex items-center overflow-x-auto scrollbar-hide">
        {tabs.map((tab, index) => {
          const TabIcon = getArtifactIcon(tab.artifact.type as ArtifactType, tab.artifact.filename);
          const isActive = index === activeIndex;
          return (
            <div
              key={tab.artifact.id}
              className={cn(
                'group relative flex items-center gap-2 px-3 py-2 border-r border-border cursor-pointer transition-colors',
                'min-w-0 max-w-[180px]',
                isActive
                  ? 'bg-background text-foreground'
                  : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground',
              )}
              onClick={() => onSwitchTab(index)}
              role="tab"
              aria-selected={isActive}
              tabIndex={isActive ? 0 : -1}
            >
              <TabIcon className="w-3.5 h-3.5 flex-shrink-0" />
              <span className="text-xs font-medium truncate">{tab.artifact.filename}</span>
              <button
                className={cn(
                  'ml-auto p-0.5 rounded hover:bg-muted-foreground/20 transition-colors',
                  'opacity-0 group-hover:opacity-100',
                  isActive && 'opacity-100',
                )}
                onClick={(e) => {
                  e.stopPropagation();
                  onCloseTab(index);
                }}
                aria-label={`${labels.close} ${tab.artifact.filename}`}
              >
                <X className="w-3 h-3" />
              </button>
              {tab.isGenerating && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary animate-pulse" />}
              {isActive && <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-primary" />}
            </div>
          );
        })}

        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              className="flex-shrink-0 p-2 text-muted-foreground hover:text-foreground hover:bg-muted/50 transition-colors"
              aria-label={labels.closeOthers}
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => onCloseOtherTabs(activeIndex)} disabled={tabs.length <= 1}>
              {labels.closeOthers}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={onCloseAllTabs} className="text-destructive">
              {labels.closeAll}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
};

export default PortalTabs;
