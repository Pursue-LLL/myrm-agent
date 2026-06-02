'use client';

import { useGlobalEvents } from '@/hooks/useGlobalEvents';
import { usePendingApprovalsRecovery } from '@/hooks/usePendingApprovalsRecovery';

/**
 * Mounts the global SSE event listener and pending approvals recovery at layout level.
 * Renders nothing — purely a side-effect component.
 */
export default function GlobalEventsInitializer() {
  useGlobalEvents();
  usePendingApprovalsRecovery();
  return null;
}
