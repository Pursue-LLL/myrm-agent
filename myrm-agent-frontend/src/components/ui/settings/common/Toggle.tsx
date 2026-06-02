'use client';

import { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { IconLoader } from '@/components/ui/icons/PremiumIcons';

interface ToggleProps {
  checked: boolean;
  isLoading?: boolean;
  disabled?: boolean;
  onChange: () => void;
  size?: 'sm' | 'md';
  ariaLabel?: string;
  autoFocus?: boolean;
}

const Toggle = memo<ToggleProps>(
  ({ checked, isLoading = false, disabled = false, onChange, size = 'md', ariaLabel, autoFocus }) => {
    const sizeClasses = size === 'sm' ? 'w-10 h-6' : 'w-12 h-7';

    const thumbSize = size === 'sm' ? 'w-4 h-4' : 'w-5 h-5';

    const thumbPosition = size === 'sm' ? { on: 'left-5', off: 'left-1' } : { on: 'left-6', off: 'left-1' };

    return (
      <button
        role="switch"
        aria-checked={checked}
        autoFocus={autoFocus}
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onChange();
        }}
        disabled={disabled || isLoading}
        aria-label={ariaLabel}
        className={cn(
          'relative rounded-full transition-all duration-300 ease-in-out',
          sizeClasses,
          isLoading ? 'bg-accent-warm/60' : checked ? 'bg-accent-warm' : 'bg-border dark:bg-muted',
          disabled && 'opacity-50 cursor-not-allowed',
        )}
      >
        {isLoading ? (
          <div className="absolute inset-0 flex items-center justify-center">
            <IconLoader className={cn('animate-spin text-white', size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4')} />
          </div>
        ) : (
          <div
            className={cn(
              'absolute top-1 rounded-full bg-white shadow-md transition-all duration-300 ease-in-out dark:shadow-black/20',
              thumbSize,
              checked ? thumbPosition.on : thumbPosition.off,
            )}
          />
        )}
      </button>
    );
  },
);

Toggle.displayName = 'Toggle';

export default Toggle;
