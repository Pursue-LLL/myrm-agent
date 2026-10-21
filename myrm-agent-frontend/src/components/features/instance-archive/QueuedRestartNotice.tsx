'use client';

/**
 * [INPUT]
 * - ./useArchiveStatus: how this deployment restarts
 * - ./RestartNotice
 *
 * [OUTPUT]
 * - QueuedRestartNotice: restart prompt for surfaces that queue a swap without owning the status
 *
 * [POS]
 * Used by the update-snapshot and storage-governance restore actions.
 */

import { memo } from 'react';
import { RestartNotice } from './RestartNotice';
import { useArchiveStatus } from './useArchiveStatus';

export const QueuedRestartNotice = memo(function QueuedRestartNotice() {
  const { status } = useArchiveStatus();
  return <RestartNotice mode={status?.restart_mode ?? 'process'} />;
});
