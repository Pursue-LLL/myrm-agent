'use client';

import { memo } from 'react';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';

interface MainToggleProps {
  enabled: boolean;
  isLoading: boolean;
  disabled: boolean;
  disabledReason?: string;
  onToggle: () => void;
}

// 主开关组件 - 使用开关样式
export const MainToggle = memo<MainToggleProps>(({
  enabled,
  isLoading,
  disabled,
  disabledReason,
  onToggle,
}) => {
  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={onToggle}
        disabled={disabled || isLoading}
        className={cn(
          'relative w-14 h-8 rounded-full transition-all duration-300 ease-in-out',
          isLoading ? 'bg-accent-warm/60' : enabled ? 'bg-accent-warm' : 'bg-border',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
        title={disabled ? disabledReason : undefined}
      >
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2 className="w-4 h-4 animate-spin text-white" />
          </div>
        ) : (
          <div
            className={cn(
              'absolute top-1 w-6 h-6 rounded-full bg-white shadow-md transition-all duration-300 ease-in-out',
              enabled ? 'left-7' : 'left-1',
            )}
          />
        )}
      </button>
      {disabled && disabledReason && (
        <span className="text-xs text-muted-foreground max-w-[150px] text-right">{disabledReason}</span>
      )}
    </div>
  );
});

MainToggle.displayName = 'MainToggle';
export default MainToggle;
