'use client';

import React from 'react';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import DesktopControlApprovalBanner from './DesktopControlApprovalBanner';

/**
 * Always-mounted approval surface for desktop control SSE requests.
 * Keeps Allow/Deny controls reachable even before DesktopLiveView chunk loads.
 */
const DesktopControlApprovalOverlay: React.FC = () => {
  const pending = useDesktopControlApprovalStore((state) => state.pending);
  if (!pending) return null;

  return (
    <div className="fixed bottom-4 left-1/2 z-[60] w-[min(100%-1.5rem,32rem)] -translate-x-1/2 pointer-events-auto">
      <DesktopControlApprovalBanner />
    </div>
  );
};

export default React.memo(DesktopControlApprovalOverlay);
