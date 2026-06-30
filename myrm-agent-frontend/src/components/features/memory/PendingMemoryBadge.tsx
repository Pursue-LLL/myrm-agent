'use client';

import { memo, useEffect, useRef } from 'react';
import { AlertTriangle, Brain } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore } from '@/store/memory';
import { toast } from '@/hooks/useToast';

interface PendingMemoryBadgeProps {
  onClick?: () => void;
  className?: string;
  showIcon?: boolean;
}

const PendingMemoryBadge = memo<PendingMemoryBadgeProps>(({ onClick, className, showIcon = true }) => {
  const pendingCount = useMemoryStore((state) => state.pendingCount);
  const conflictCount = useMemoryStore((state) => state.conflictCount);
  const prevConflictCount = useRef(conflictCount);

  useEffect(() => {
    if (conflictCount > prevConflictCount.current && prevConflictCount.current === 0) {
      toast({
        title: '检测到记忆冲突',
        description: `发现 ${conflictCount} 条记忆冲突，请在记忆管理中查看并裁决`,
        variant: 'default',
      });
    }
    prevConflictCount.current = conflictCount;
  }, [conflictCount]);

  const totalCount = pendingCount + conflictCount;

  if (totalCount === 0) return null;

  return (
    <button
      onClick={onClick}
      className={cn(
        'relative inline-flex items-center justify-center',
        'transition-all duration-300 ease-out',
        'hover:scale-105 active:scale-95',
        className,
      )}
    >
      {showIcon && (
        <div className="relative">
          {conflictCount > 0 ? (
            <AlertTriangle size={20} className="text-amber-500 animate-pulse" />
          ) : (
            <Brain size={20} className={cn('text-primary', pendingCount > 0 && 'animate-pulse')} />
          )}
          <div
            className={cn(
              'absolute inset-0 blur-md rounded-full animate-pulse',
              conflictCount > 0 ? 'bg-amber-500/20' : 'bg-primary/20',
            )}
          />
        </div>
      )}

      <span
        className={cn(
          'absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px]',
          'flex items-center justify-center',
          'text-[10px] font-bold text-white',
          'rounded-full px-1',
          'animate-in zoom-in-50 duration-300',
          conflictCount > 0
            ? 'bg-gradient-to-br from-amber-500 to-orange-600 shadow-lg shadow-amber-500/30'
            : 'bg-gradient-to-br from-red-500 to-rose-600 shadow-lg shadow-red-500/30',
        )}
      >
        {totalCount > 99 ? '99+' : totalCount}
      </span>
    </button>
  );
});

PendingMemoryBadge.displayName = 'PendingMemoryBadge';

export default PendingMemoryBadge;
