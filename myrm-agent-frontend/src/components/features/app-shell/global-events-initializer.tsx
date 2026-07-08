'use client';

import { useGlobalEvents } from '@/hooks/useGlobalEvents';
import { usePendingApprovalsRecovery } from '@/hooks/usePendingApprovalsRecovery';
import { useWorkspaceStream } from '@/hooks/useWorkspaceStream';

/**
 * Mounts the global SSE event listener and pending approvals recovery at layout level.
 * Renders nothing — purely a side-effect component.
 */
export default function GlobalEventsInitializer() {
  useWorkspaceStream();
  useGlobalEvents();
  usePendingApprovalsRecovery();
  return null;
}
