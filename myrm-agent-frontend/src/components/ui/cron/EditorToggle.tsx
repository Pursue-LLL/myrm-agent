'use client';

import { cn } from '@/lib/utils/classnameUtils';

interface EditorToggleProps {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function EditorToggle({ enabled, onToggle, disabled }: EditorToggleProps) {
  return (
    <button
      onClick={onToggle}
      disabled={disabled}
      className={cn(
        'relative inline-flex h-5 w-9 items-center rounded-full transition-colors',
        enabled ? 'bg-accent-warm' : 'bg-muted',
      )}
    >
      <span
        className={cn(
          'inline-block h-3.5 w-3.5 rounded-full bg-white transition-transform',
          enabled ? 'translate-x-4.5' : 'translate-x-0.5',
        )}
      />
    </button>
  );
}
