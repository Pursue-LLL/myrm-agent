'use client';

import { useTranslations } from 'next-intl';
import { Activity, Zap } from 'lucide-react';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useShallow } from 'zustand/react/shallow';
import { cn } from '@/lib/utils/classnameUtils';

export default function ActiveSessionsBar() {
  const t = useTranslations('multiPane');
  const { activeSessions, maxConcurrent, availableSlots } = useWorkspaceStore(
    useShallow((s) => ({
      activeSessions: s.activeSessions,
      maxConcurrent: s.maxConcurrent,
      availableSlots: s.availableSlots,
    })),
  );

  const runningCount = activeSessions.length;

  return (
    <div className="flex items-center gap-3 text-sm text-muted-foreground">
      <div className="flex items-center gap-1.5">
        <Activity size={14} className={cn(runningCount > 0 ? 'text-green-500' : 'text-muted-foreground')} />
        <span>
          {t('activeAgents')}: {runningCount}/{maxConcurrent}
        </span>
      </div>
      <div className="flex items-center gap-1.5">
        <Zap size={14} />
        <span>{t('slotsAvailable', { count: availableSlots })}</span>
      </div>
    </div>
  );
}
