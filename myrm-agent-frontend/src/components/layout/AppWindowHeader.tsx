/**
 * [INPUT]
 * - @/hooks/ui/useWindowControls::useWindowControls
 * - @/lib/utils/classnameUtils::cn
 *
 * [OUTPUT]
 * - AppWindowHeader: Non-intrusive drag region and traffic-light placeholder component
 *
 * [POS]
 * Renders an invisible or adaptive drag bar for Tauri desktop while preserving 100% zero-space
 * purity in standard Web and Mobile viewports.
 */

'use client';

import { memo } from 'react';
import { useWindowControls } from '@/hooks/ui/useWindowControls';
import { cn } from '@/lib/utils/classnameUtils';

interface AppWindowHeaderProps {
  className?: string;
}

export const AppWindowHeader = memo<AppWindowHeaderProps>(({ className }) => {
  const { isDesktop, controlsInsetTop, platform } = useWindowControls();

  if (!isDesktop || controlsInsetTop <= 0) {
    return null;
  }

  return (
    <div
      data-tauri-drag-region
      className={cn(
        'w-full select-none shrink-0 pointer-events-auto z-50',
        platform === 'macos' ? 'h-[28px]' : 'h-[32px]',
        className,
      )}
      aria-hidden="true"
    />
  );
});

AppWindowHeader.displayName = 'AppWindowHeader';
export default AppWindowHeader;
