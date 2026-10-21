import React, { ReactNode } from 'react';
import { Tooltip as TooltipPrimitive, TooltipContent, TooltipTrigger } from '@/components/primitives/tooltip';
import { cn } from '@/lib/utils/classnameUtils';

interface TooltipProps {
  children: ReactNode;
  content: ReactNode;
  className?: string;
  delayDuration?: number;
}

const Tooltip: React.FC<TooltipProps> = ({
  children,
  content,
  className,
  delayDuration = 0, // 立即显示，便于测试
}) => {
  return (
    <TooltipPrimitive delayDuration={delayDuration}>
      <TooltipTrigger asChild>{children}</TooltipTrigger>
      <TooltipContent
        className={cn(
          'z-50 overflow-hidden rounded-lg bg-white dark:bg-gray-800 px-4 py-3 text-sm text-gray-900 dark:text-gray-100 shadow-lg border border-gray-200 dark:border-gray-700 min-w-[280px] max-w-[400px]',
          '[&_a]:text-blue-600 [&_a]:hover:text-blue-800 [&_a]:underline [&_a]:cursor-pointer dark:[&_a]:text-blue-400 dark:[&_a]:hover:text-blue-300',
          '[&_code]:bg-gray-100 [&_code]:dark:bg-gray-700 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:rounded [&_code]:text-xs [&_code]:font-mono',
          '[&_ul]:mt-2 [&_li]:mt-1',
          className,
        )}
        sideOffset={5}
        onClick={(e) => e.stopPropagation()}
      >
        {content}
      </TooltipContent>
    </TooltipPrimitive>
  );
};

export default Tooltip;
