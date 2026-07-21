import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { useTranslations } from 'next-intl';
import { FolderSearch, SearchCode } from 'lucide-react';
import type { SearchToolItem } from '../utils';

interface SearchToolCardProps {
  items: SearchToolItem[];
  toolName?: string | null;
  messageId: string;
  stepIndex: number;
}

const SearchToolCard: React.FC<SearchToolCardProps> = ({ items, toolName, messageId, stepIndex }) => {
  const t = useTranslations('progressSteps.searchTool');
  const isGlob = toolName === 'glob_tool';

  return (
    <div className="flex flex-col gap-2">
      {items.map((item, itemIndex) => (
        <div
          key={`${messageId}-search-${stepIndex}-${itemIndex}`}
          className={cn(
            'rounded-lg border border-border/60 bg-muted/30 px-3 py-2',
            'text-xs sm:text-sm space-y-1.5',
          )}
        >
          <div className="flex items-center gap-2 text-muted-foreground">
            {isGlob ? <FolderSearch className="w-3.5 h-3.5 shrink-0" /> : <SearchCode className="w-3.5 h-3.5 shrink-0" />}
            <span className="font-medium text-foreground/80">{isGlob ? t('globLabel') : t('grepLabel')}</span>
          </div>
          <div className="font-mono text-[11px] sm:text-xs break-all text-foreground bg-background/60 rounded-md px-2 py-1.5 border border-border/40">
            {item.pattern}
          </div>
          <div className="flex flex-wrap gap-2 text-[10px] sm:text-[11px] text-muted-foreground">
            <span>
              {t('path')}: <span className="font-mono text-foreground/70">{item.search_path || '.'}</span>
            </span>
            {item.file_pattern && (
              <span>
                {t('filePattern')}: <span className="font-mono text-foreground/70">{item.file_pattern}</span>
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default SearchToolCard;
