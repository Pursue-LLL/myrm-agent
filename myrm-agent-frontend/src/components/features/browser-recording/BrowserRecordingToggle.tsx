'use client';

import React from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import { Circle } from 'lucide-react';
import useBrowserRecordingStore from '@/store/useBrowserRecordingStore';

const BrowserRecordingToggle: React.FC = () => {
  const { isOpen, status, togglePanel, steps } = useBrowserRecordingStore();

  const isActive = status === 'recording' || status === 'paused';

  return (
    <button
      type="button"
      onClick={togglePanel}
      className={cn(
        'fixed bottom-24 right-6 p-3 rounded-full shadow-lg transition-colors z-50',
        'flex items-center justify-center gap-1.5',
        'max-sm:bottom-20 max-sm:right-4',
        isOpen
          ? 'bg-destructive text-destructive-foreground ring-2 ring-destructive/30'
          : isActive
            ? 'bg-destructive text-destructive-foreground animate-pulse'
            : 'bg-secondary text-secondary-foreground hover:bg-secondary/90',
      )}
      title="Browser Recording"
      aria-label="Toggle browser recording panel"
    >
      <Circle size={18} fill={isActive ? 'currentColor' : 'none'} />
      {isActive && steps.length > 0 && (
        <span className="text-xs font-mono font-bold">{steps.length}</span>
      )}
    </button>
  );
};

export default React.memo(BrowserRecordingToggle);
