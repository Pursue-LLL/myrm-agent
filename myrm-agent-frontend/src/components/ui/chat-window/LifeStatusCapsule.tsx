'use client';

import { useEffect, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { IconCheckCircle, IconX } from '@/components/ui/icons/PremiumIcons';

interface IdleStatusData {
  session_id: string;
  status: 'working' | 'completed' | 'error' | 'idle';
  task_name?: string;
  message?: string;
  progress_pct?: number;
}

export function LifeStatusCapsule({ currentSessionId }: { currentSessionId: string | null }) {
  const [statusData, setStatusData] = useState<IdleStatusData | null>(null);

  useEffect(() => {
    const handleIdleStatus = (e: CustomEvent<IdleStatusData>) => {
      const data = e.detail;
      // Only show status if it belongs to the current session (or no session filter is applied if you want it global)
      if (data.session_id === currentSessionId || data.session_id === 'global' || data.status === 'idle') {
        if (data.status === 'idle') {
          // Keep it around for a moment then fade out, or just hide immediately
          setStatusData(null);
        } else {
          setStatusData(data);
        }
      }
    };

    window.addEventListener('idle-status', handleIdleStatus as EventListener);
    return () => {
      window.removeEventListener('idle-status', handleIdleStatus as EventListener);
    };
  }, [currentSessionId]);

  if (!statusData) {
    return null;
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: 10, scale: 0.95 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        exit={{ opacity: 0, y: 10, scale: 0.95 }}
        transition={{ duration: 0.3 }}
        className="fixed bottom-24 right-8 z-50 flex items-center gap-3 rounded-full border border-primary/20 bg-background/80 px-4 py-2 text-sm shadow-lg backdrop-blur-md dark:bg-muted/80"
      >
        {statusData.status === 'working' && (
          <span className="relative flex h-3 w-3">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary opacity-75"></span>
            <span className="relative inline-flex h-3 w-3 rounded-full bg-primary"></span>
          </span>
        )}
        {statusData.status === 'completed' && (
          <span className="text-green-500">
            <IconCheckCircle />
          </span>
        )}
        {statusData.status === 'error' && (
          <span className="text-red-500">
            <IconX />
          </span>
        )}

        <span className="font-medium text-foreground/90">{statusData.message || 'Processing background tasks...'}</span>

        {typeof statusData.progress_pct === 'number' && (
          <span className="text-xs text-muted-foreground">{statusData.progress_pct}%</span>
        )}
      </motion.div>
    </AnimatePresence>
  );
}
