'use client';

import { useGlobalEvents } from '@/hooks/globalEvents/useGlobalEvents';
import { usePendingApprovalsRecovery } from '@/hooks/approval/usePendingApprovalsRecovery';
import { useWorkspaceStream } from '@/hooks/workspace/useWorkspaceStream';

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
