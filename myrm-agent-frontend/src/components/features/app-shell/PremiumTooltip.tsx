import React from 'react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives/tooltip';

interface PremiumTooltipProps {
  children: React.ReactNode;
  tooltipContent: React.ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
  align?: 'start' | 'center' | 'end';
}

export function PremiumTooltip({ children, tooltipContent, side = 'top', align = 'center' }: PremiumTooltipProps) {
  if (!tooltipContent) return <>{children}</>;

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
        <TooltipTrigger asChild>{children}</TooltipTrigger>
        <TooltipContent
          side={side}
          align={align}
          className="bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900 shadow-xl font-medium tracking-wide"
        >
          {tooltipContent}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
