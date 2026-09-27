import React from 'react';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import DesktopControlApprovalBanner from './DesktopControlApprovalBanner';
import { LeaseProgressCapsule } from '@/components/chat-window/approval/LeaseProgressCapsule';

/**
 * Always-mounted approval surface for desktop control SSE requests and active envelopes.
 * Keeps Allow/Deny controls and in-place lease HUD reachable.
 */
const DesktopControlApprovalOverlay: React.FC = () => {
  const pending = useDesktopControlApprovalStore((state) => state.pending);
  const activeEnvelope = useDesktopControlApprovalStore((state) => state.activeEnvelope);

  if (!pending && (!activeEnvelope || activeEnvelope.status === 'completed')) {
    return null;
  }

  return (
    <div className="fixed bottom-4 left-1/2 z-[60] flex flex-col items-center gap-2 -translate-x-1/2 pointer-events-auto w-[min(100%-1.5rem,32rem)]">
      {activeEnvelope && activeEnvelope.status === 'active' && !pending && (
        <LeaseProgressCapsule />
      )}
      {pending && <DesktopControlApprovalBanner />}
    </div>
  );
};

export default React.memo(DesktopControlApprovalOverlay);
