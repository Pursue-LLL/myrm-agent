'use client';

import { memo } from 'react';
import { cn } from '@/lib/utils/classnameUtils';

interface StatCardProps {
  icon: React.ElementType;
  label: string;
  value: string;
  subValue?: string;
  colorClass: string;
}

export const StatCard = memo<StatCardProps>(({ icon: Icon, label, value, subValue, colorClass }) => (
  <div className="flex flex-col gap-2 p-4 rounded-xl bg-background/60 border border-border/40">
    <div className="flex items-center gap-2">
      <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center', colorClass)}>
        <Icon className="w-4 h-4 text-inherit" />
      </div>
      <span className="text-xs text-muted-foreground font-medium">{label}</span>
    </div>
    <div className="flex items-baseline gap-1.5">
      <span className="text-xl font-bold tabular-nums text-foreground">{value}</span>
      {subValue && <span className="text-xs text-muted-foreground">{subValue}</span>}
    </div>
  </div>
));
StatCard.displayName = 'StatCard';
