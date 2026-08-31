'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Eye, MousePointerClick, RefreshCw, X, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';

type InspectorMode = 'view' | 'inspect';

interface DeviceInspectorToolbarProps {
  mode: InspectorMode;
  notificationRedaction: boolean;
  onModeChange: (mode: InspectorMode) => void;
  onToggleNotificationRedaction: (enabled: boolean) => void;
  onClose: () => void;
  onRefresh?: () => void;
  isLoading?: boolean;
  title?: string;
  subtitle?: string;
}

const DeviceInspectorToolbar: React.FC<DeviceInspectorToolbarProps> = ({
  mode,
  notificationRedaction,
  onModeChange,
  onToggleNotificationRedaction,
  onClose,
  onRefresh,
  isLoading,
  title,
  subtitle,
}) => {
  const t = useTranslations('chat.deviceInspector');

  return (
    <div className="flex items-center justify-between px-3 py-1.5 bg-muted border-b border-border min-h-[36px]">
      <div className="flex flex-col min-w-0">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span className="text-sm font-medium text-foreground truncate max-w-[200px]">{title || t('title')}</span>
        </div>
        {subtitle && <span className="text-[11px] text-muted-foreground truncate max-w-[200px] pl-4">{subtitle}</span>}
      </div>

      <div className="flex items-center gap-1">
        <button
          type="button"
          onClick={() => onToggleNotificationRedaction(!notificationRedaction)}
          className={cn(
            'px-2 py-1 text-xs rounded-md transition-colors flex items-center gap-1',
            notificationRedaction
              ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 font-medium'
              : 'text-muted-foreground hover:text-foreground hover:bg-muted-foreground/10',
          )}
          title={t('notificationRedaction')}
        >
          {notificationRedaction ? <ShieldCheck className="w-3.5 h-3.5" /> : <ShieldAlert className="w-3.5 h-3.5" />}
          <span className="text-[10px] max-sm:hidden">{t('redactionBadge')}</span>
        </button>

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

        {onRefresh && (
          <button
            type="button"
            onClick={onRefresh}
            disabled={isLoading}
            className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted-foreground/10 rounded-md transition-colors disabled:opacity-50"
            title={t('refresh')}
          >
            <RefreshCw className={cn('w-3.5 h-3.5', isLoading && 'animate-spin')} />
          </button>
        )}

        <button
          type="button"
          onClick={onClose}
          className="p-1 text-muted-foreground hover:text-foreground hover:bg-muted-foreground/10 rounded-md transition-colors"
          title={t('close')}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
};

export default DeviceInspectorToolbar;
