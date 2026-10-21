'use client';

import BrandLogo from '@/components/features/app-shell/BrandLogo';
import { cn } from '@/lib/utils/classnameUtils';

interface AppShellSkeletonProps {
  className?: string;
}

export default function AppShellSkeleton({ className }: AppShellSkeletonProps) {
  return (
    <div
      data-testid="app-shell-skeleton"
      className={cn('min-h-[100dvh] bg-background text-foreground', className)}
      aria-busy="true"
      aria-live="polite"
    >
      <div className="flex min-h-[100dvh] flex-col items-center justify-center gap-4 px-6">
        <BrandLogo size={48} />
        <div className="h-1 w-24 overflow-hidden rounded-full bg-muted">
          <div className="h-full w-1/2 animate-pulse rounded-full bg-primary/70" />
        </div>
      </div>
    </div>
  );
}
