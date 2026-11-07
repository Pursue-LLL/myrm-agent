'use client';

/**
 * [INPUT] @/components/primitives/tooltip (POS: 状态徽标的悬浮说明)
 * [OUTPUT] RemarkPopover: Key 备注编辑浮层；HealthBadge / KeyHealthState: 单把 Key 的连通性徽标及其状态
 * [POS] ApiKeyManager 的展示部件，状态与探测流程都由 ApiKeyManager 持有，这里只负责渲染与备注输入。
 */

import { memo, useState, useRef, useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { Check, X, RefreshCw, Loader2 } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';

type KeyHealthStatus = 'unchecked' | 'checking' | 'valid' | 'invalid';

export interface KeyHealthState {
  status: KeyHealthStatus;
  error?: string;
  latencyMs?: number;
}

export const RemarkPopover = memo<{
  remark: string;
  onSave: (remark: string) => void;
  onClose: () => void;
}>(({ remark, onSave, onClose }) => {
  const [value, setValue] = useState(remark);
  const inputRef = useRef<HTMLInputElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [onClose]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      onSave(value);
    } else if (e.key === 'Escape') {
      onClose();
    }
  };

  return (
    <div
      ref={popoverRef}
      className="absolute top-full left-0 mt-1 z-50 p-3 bg-popover border border-border rounded-lg shadow-lg min-w-[200px] animate-in fade-in-0 zoom-in-95 duration-150"
    >
      <div className="flex items-center gap-2">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          className="flex-1 text-sm bg-background border border-border rounded-full px-2 py-1.5 focus:outline-none focus:ring-2 focus:ring-primary/30"
        />
        <button
          onClick={() => onSave(value)}
          className="p-1.5 text-primary hover:bg-primary/10 rounded-full transition-colors"
        >
          <Check className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onClose}
          className="p-1.5 text-muted-foreground hover:bg-accent rounded-full transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
});
RemarkPopover.displayName = 'RemarkPopover';

export const HealthBadge = memo<{ health: KeyHealthState; onRetry?: () => void }>(({ health, onRetry }) => {
  const t = useTranslations('settings.modelService');

  if (health.status === 'unchecked') {
    return null;
  }

  if (health.status === 'checking') {
    return <Loader2 className="w-3.5 h-3.5 animate-spin text-muted-foreground flex-shrink-0" />;
  }

  if (health.status === 'valid') {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="flex items-center gap-1 text-xs text-green-600 dark:text-green-400 flex-shrink-0">
            <Check className="w-3 h-3" />
            {health.latencyMs !== null && health.latencyMs !== undefined && `${health.latencyMs}ms`}
          </span>
        </TooltipTrigger>
        <TooltipContent>{t('keyVerified')}</TooltipContent>
      </Tooltip>
    );
  }

  return (
    <div className="flex items-center gap-1 flex-shrink-0">
      <Tooltip>
        <TooltipTrigger asChild>
          <span className="text-xs text-destructive-text truncate max-w-[120px]">
            {health.error || t('keyInvalid')}
          </span>
        </TooltipTrigger>
        <TooltipContent>{health.error || t('keyInvalid')}</TooltipContent>
      </Tooltip>
      {onRetry && (
        <button
          onClick={onRetry}
          className="p-0.5 text-muted-foreground hover:text-primary transition-colors"
          title={t('retryVerify')}
        >
          <RefreshCw className="w-3 h-3" />
        </button>
      )}
    </div>
  );
});
HealthBadge.displayName = 'HealthBadge';
