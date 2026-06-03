'use client';

import { memo } from 'react';
import { Brain } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import { useMemoryStore } from '@/store/memory';

interface PendingMemoryBadgeProps {
  onClick?: () => void;
  className?: string;
  showIcon?: boolean;
}

const PendingMemoryBadge = memo<PendingMemoryBadgeProps>(({ onClick, className, showIcon = true }) => {
  // 只消费 pendingCount 数据，不启动轮询
  // 轮询由 UserMenu 统一管理，避免重复启动
  const pendingCount = useMemoryStore((state) => state.pendingCount);

  if (pendingCount === 0) return null;

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
          <Brain size={20} className={cn('text-primary', pendingCount > 0 && 'animate-pulse')} />

          {/* 发光效果 */}
          <div className="absolute inset-0 bg-primary/20 blur-md rounded-full animate-pulse" />
        </div>
      )}

      {/* 数量徽章 */}
      <span
        className={cn(
          'absolute -top-1.5 -right-1.5 min-w-[18px] h-[18px]',
          'flex items-center justify-center',
          'text-[10px] font-bold text-white',
          'bg-gradient-to-br from-red-500 to-rose-600',
          'rounded-full px-1',
          'shadow-lg shadow-red-500/30',
          'animate-in zoom-in-50 duration-300',
        )}
      >
        {pendingCount > 99 ? '99+' : pendingCount}
      </span>
    </button>
  );
});

PendingMemoryBadge.displayName = 'PendingMemoryBadge';

export default PendingMemoryBadge;
