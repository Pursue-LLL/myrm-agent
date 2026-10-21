'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive::instanceArchiveService (POS: instance archive HTTP client)
 *
 * [OUTPUT]
 * - useInstanceExport: export state machine (idle, running, ready, downloading, saved) with start / save / discard
 *
 * [POS]
 * Drives the export card: starts a backup job, polls it to completion, then streams the finished
 * file to disk. Errors surface as stable codes, never server wording.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { archiveErrorCode, instanceArchiveService, type ExportJob } from '@/services/instanceArchive';

export type ExportPhase =
  | { kind: 'idle'; errorCode?: string }
  | { kind: 'running'; job: ExportJob }
  | { kind: 'ready'; job: ExportJob; errorCode?: string }
  | { kind: 'downloading'; job: ExportJob; received: number }
  | { kind: 'saved'; job: ExportJob };

const POLL_INTERVAL_MS = 700;

const sleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

export function useInstanceExport() {
  const [phase, setPhase] = useState<ExportPhase>({ kind: 'idle' });
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const update = useCallback((next: ExportPhase) => {
    if (mounted.current) {
      setPhase(next);
    }
  }, []);

  const start = useCallback(
    async (passphrase?: string) => {
      try {
        let job = await instanceArchiveService.startExport(passphrase);
        update({ kind: 'running', job });
        while (mounted.current && job.state === 'running') {
          await sleep(POLL_INTERVAL_MS);
          job = await instanceArchiveService.getExport(job.job_id);
          update({ kind: 'running', job });
        }
        if (job.state === 'done') {
          update({ kind: 'ready', job });
        } else if (job.state !== 'running') {
          update({ kind: 'idle', errorCode: job.state === 'failed' ? (job.error_code ?? 'export_failed') : undefined });
        }
      } catch (error) {
        update({ kind: 'idle', errorCode: archiveErrorCode(error) });
      }
    },
    [update],
  );

  const save = useCallback(
    async (job: ExportJob) => {
      update({ kind: 'downloading', job, received: 0 });
      try {
        const outcome = await instanceArchiveService.downloadExport(job.job_id, (received) =>
          update({ kind: 'downloading', job, received }),
        );
        update(outcome === 'saved' ? { kind: 'saved', job } : { kind: 'ready', job });
      } catch (error) {
        update({ kind: 'ready', job, errorCode: archiveErrorCode(error) });
      }
    },
    [update],
  );

  const discard = useCallback(
    async (job: ExportJob) => {
      await instanceArchiveService.discardExport(job.job_id).catch(() => undefined);
      update({ kind: 'idle' });
    },
    [update],
  );

  return { phase, start, save, discard };
}
