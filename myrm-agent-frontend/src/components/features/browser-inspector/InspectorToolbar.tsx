'use client';

/**
 * [INPUT]
 * @/lib/utils/classnameUtils::cn (POS: Tailwind class name utilities)
 *
 * [OUTPUT]
 * InspectorToolbar: Toolbar with mode toggle, page info, refresh, and sandbox desktop takeover.
 *
 * [POS]
 * Browser Inspector toolbar. Controls inspector view modes, navigation hints, and sandbox desktop takeover.
 */

import React, { useCallback } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Eye, MousePointerClick, X, RefreshCw, ExternalLink, MonitorPlay } from 'lucide-react';
import { useTranslations } from 'next-intl';

type InspectorMode = 'view' | 'inspect';

interface InspectorToolbarProps {
  mode: InspectorMode;
  onModeChange: (mode: InspectorMode) => void;
  onClose: () => void;
  onRefresh?: () => void;
  pageUrl?: string;
  pageTitle?: string;
  isLoading?: boolean;
}

const InspectorToolbar: React.FC<InspectorToolbarProps> = ({
  mode,
  onModeChange,
  onClose,
  onRefresh,
  pageUrl,
  pageTitle,
  isLoading,
}) => {
  const t = useTranslations('chat.browserInspector');

  const handleTakeoverDesktop = useCallback(() => {
    if (typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('open_visual_desktop'));
    }
    onClose();
  }, [onClose]);

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-muted border-b border-border min-h-[36px]">
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full bg-chart-2 animate-pulse" />
        <span className="text-sm font-medium text-foreground truncate max-w-[200px]">{pageTitle || t('title')}</span>
        {pageUrl && (
          <a
            href={pageUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground transition-colors"
            title={pageUrl}
          >
            <ExternalLink className="w-3.5 h-3.5" />
          </a>
        )}
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onModeChange('view')}
          className={cn(
            'px-2 py-1 text-xs rounded-md transition-colors',
            mode === 'view'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted-foreground/10',
          )}
          title={t('viewMode')}
        >
          <Eye className="w-3.5 h-3.5" />
        </button>

        <button
          type="button"
          onClick={() => onModeChange('inspect')}
          className={cn(
            'px-2 py-1 text-xs rounded-md transition-colors',
            mode === 'inspect'
              ? 'bg-primary text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted-foreground/10',
          )}
          title={t('inspectMode')}
        >
          <MousePointerClick className="w-3.5 h-3.5" />
        </button>

        <div className="w-px h-4 bg-border mx-1" />

        <button
          type="button"
          onClick={handleTakeoverDesktop}
          className="p-1 text-muted-foreground hover:text-foreground transition-colors hover:bg-muted-foreground/10 rounded-md"
          title="Takeover Sandbox Desktop"
          aria-label="Takeover Sandbox Desktop"
          data-testid="inspector-takeover-desktop-button"
        >
          <MonitorPlay className="w-3.5 h-3.5" />
        </button>

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="p-1 text-muted-foreground hover:text-foreground transition-colors hover:bg-muted-foreground/10 rounded-md"
            title={t('refresh')}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          </button>
        )}

        <button
          type="button"
          onClick={onClose}
          className="p-1 text-muted-foreground hover:text-foreground transition-colors hover:bg-muted-foreground/10 rounded-md"
          title={t('close')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default React.memo(InspectorToolbar);
