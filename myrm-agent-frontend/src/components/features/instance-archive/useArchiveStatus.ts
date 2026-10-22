'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive::instanceArchiveService (POS: instance archive HTTP client)
 *
 * [OUTPUT]
 * - useArchiveStatus: what this workspace can do (restart mode, supported operations) plus a reload handle
 *
 * [POS]
 * Single answer to "what can this workspace do" shared by the backup cards and restart notices.
 */

import { useCallback, useEffect, useState } from 'react';
import { instanceArchiveService, type ArchiveStatus } from '@/services/instanceArchive';

interface UseArchiveStatusResult {
  status: ArchiveStatus | null;
  reload: () => Promise<void>;
}

/** Capabilities of this workspace; `null` until the first successful load (or when the endpoint is not reachable for this identity). */
export function useArchiveStatus(): UseArchiveStatusResult {
  const [status, setStatus] = useState<ArchiveStatus | null>(null);

  const reload = useCallback(async () => {
    try {
      setStatus(await instanceArchiveService.getStatus());
    } catch {
      // Keep the last known capabilities: the backend may be restarting to apply a swap.
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return { status, reload };
}
