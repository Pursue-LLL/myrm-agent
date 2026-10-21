import React from 'react';
import { toast } from '@/lib/utils/toast';
import { Activity } from 'lucide-react';

export function showLocatorHealedToast(data: Record<string, unknown>) {
  const oldName = String(data.old_name ?? 'Unknown');
  const newName = String(data.new_name ?? 'Unknown');
  const distance = typeof data.distance === 'number' ? data.distance.toFixed(1) : '0.0';

  toast.info(
    <div className="flex flex-col gap-1.5 w-full">
      <div className="flex items-center gap-2 font-semibold text-emerald-500 dark:text-emerald-400">
        <Activity className="h-4 w-4 animate-pulse" />
        <span>Self-Healing Activated</span>
      </div>
      <div className="text-sm text-muted-foreground leading-relaxed">
        The agent automatically recovered a broken locator via spatial footprint matching.
      </div>
      <div className="mt-1 rounded-md bg-muted/50 p-2 text-xs font-mono border border-border/50">
        <div className="flex justify-between items-center mb-1 text-muted-foreground">
          <span>Target</span>
          <span className="text-[10px] bg-background px-1.5 py-0.5 rounded border">Δ {distance}px</span>
        </div>
        <div className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1">
          <span className="text-destructive/80 line-through truncate max-w-[120px]" title={oldName}>
            {oldName}
          </span>
          <span className="text-emerald-600 dark:text-emerald-400 truncate font-medium max-w-[120px]" title={newName}>
            → {newName}
          </span>
        </div>
      </div>
    </div>,
    {
      duration: 8000,
    },
  );
}
