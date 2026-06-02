'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Eye, MousePointerClick, RefreshCw, X } from 'lucide-react';
import { useTranslations } from 'next-intl';

type InspectorMode = 'view' | 'inspect';

interface DesktopInspectorToolbarProps {
  mode: InspectorMode;
  onModeChange: (mode: InspectorMode) => void;
  onClose: () => void;
  onRefresh?: () => void;
  isLoading?: boolean;
  title?: string;
  subtitle?: string;
}

const DesktopInspectorToolbar: React.FC<DesktopInspectorToolbarProps> = ({
  mode,
  onModeChange,
  onClose,
  onRefresh,
  isLoading,
  title,
  subtitle,
}) => {
  const t = useTranslations('chat.desktopInspector');

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-muted border-b border-border min-h-[36px]">
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-chart-4 animate-pulse" />
          <span className="text-sm font-medium text-foreground truncate max-w-[220px]">{title || t('title')}</span>
        </div>
        {subtitle && <span className="text-[11px] text-muted-foreground truncate max-w-[220px] pl-4">{subtitle}</span>}
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

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            className="p-1 text-muted-foreground hover:text-foreground transition-colors"
            title={t('refresh')}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          </button>
        )}

        <button
          type="button"
          onClick={onClose}
          className="p-1 text-muted-foreground hover:text-foreground transition-colors"
          title={t('close')}
        >
          <X className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};

export default React.memo(DesktopInspectorToolbar);
