/**
 * [INPUT]
 * @/components/features/chat-window/MessageListSkeleton (POS: 聊天消息列表骨架屏)
 * @/components/features/settings/common/SettingsSkeleton (POS: 设置页通用骨架屏)
 *
 * [OUTPUT]
 * RouteSegmentLoading: Unified instant-navigation fallback shells for major route segments.
 *
 * [POS]
 * Layout-layer loading UI for Next.js `loading.tsx` routes under the Navigation Shell Contract.
 */
import MessageListSkeleton from '@/components/features/chat-window/MessageListSkeleton';
import { SettingsSkeleton } from '@/components/features/settings/common/SettingsSkeleton';
import { Skeleton } from '@/components/primitives/skeleton';
import { cn } from '@/lib/utils/classnameUtils';

type RouteSegmentLoadingVariant = 'chat' | 'settings' | 'dashboard';

interface RouteSegmentLoadingProps {
  variant?: RouteSegmentLoadingVariant;
  className?: string;
}

export default function RouteSegmentLoading({
  variant = 'dashboard',
  className,
}: RouteSegmentLoadingProps) {
  if (variant === 'chat') {
    return (
      <div
        className={cn('flex h-full min-h-[50vh] w-full flex-col px-4 pt-6', className)}
        aria-busy="true"
        aria-live="polite"
      >
        <MessageListSkeleton />
      </div>
    );
  }

  if (variant === 'settings') {
    return (
      <div className={cn('flex min-h-[50vh] w-full px-6 py-8', className)} aria-busy="true" aria-live="polite">
        <SettingsSkeleton />
      </div>
    );
  }

  return (
    <div
      className={cn('flex min-h-[50vh] w-full flex-col gap-4 px-6 py-8', className)}
      aria-busy="true"
      aria-live="polite"
    >
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-4 w-72" />
      <div className="mt-4 grid gap-3">
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
        <Skeleton className="h-24 w-full rounded-xl" />
      </div>
    </div>
  );
}
