'use client';

/**
 * [INPUT]
 * - @/services/instanceArchive::instanceArchiveService (POS: instance archive HTTP client)
 *
 * [OUTPUT]
 * - useInstanceImport: import state machine (upload, passphrase, verify, review, confirm, queued)
 *
 * [POS]
 * Drives the import card: resumable upload, backup verification, the review step, and the final
 * confirmation that queues the swap. Cancelling or leaving the page discards the staged upload.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import {
  archiveErrorCode,
  instanceArchiveService,
  type ImportReport,
  type UploadProgress,
} from '@/services/instanceArchive';

export type ImportPhase =
  | { kind: 'idle'; errorCode?: string }
  | { kind: 'uploading'; fileName: string; progress: UploadProgress }
  | { kind: 'passphrase'; sessionId: string; errorCode?: string }
  | { kind: 'verifying'; sessionId: string }
  | { kind: 'review'; sessionId: string; report: ImportReport; errorCode?: string }
  | { kind: 'confirming'; sessionId: string; report: ImportReport }
  | { kind: 'queued' };

export function useInstanceImport(onQueued: () => void) {
  const [phase, setPhase] = useState<ImportPhase>({ kind: 'idle' });
  const mounted = useRef(true);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      abort.current?.abort();
    };
  }, []);

  const update = useCallback((next: ImportPhase) => {
    if (mounted.current) {
      setPhase(next);
    }
  }, []);

  const stage = useCallback(
    async (sessionId: string, options: { passphrase?: string; skipSecrets?: boolean } = {}) => {
      update({ kind: 'verifying', sessionId });
      try {
        update({ kind: 'review', sessionId, report: await instanceArchiveService.stageImport(sessionId, options) });
      } catch (error) {
        const code = archiveErrorCode(error);
        if (code === 'passphrase_required' || code === 'wrong_passphrase') {
          update({ kind: 'passphrase', sessionId, errorCode: code === 'wrong_passphrase' ? code : undefined });
        } else {
          await instanceArchiveService.cancelImport(sessionId).catch(() => undefined);
          update({ kind: 'idle', errorCode: code });
        }
      }
    },
    [update],
  );

  const upload = useCallback(
    async (file: File) => {
      abort.current?.abort();
      const controller = new AbortController();
      abort.current = controller;
      update({ kind: 'uploading', fileName: file.name, progress: { chunksDone: 0, chunksTotal: 1 } });
      try {
        const session = await instanceArchiveService.uploadArchive(file, {
          signal: controller.signal,
          onProgress: (progress) => update({ kind: 'uploading', fileName: file.name, progress }),
        });
        await stage(session.session_id);
      } catch (error) {
        update({ kind: 'idle', errorCode: controller.signal.aborted ? undefined : archiveErrorCode(error) });
      }
    },
    [stage, update],
  );

  const confirm = useCallback(
    async (sessionId: string, report: ImportReport, acknowledgeExecutables: boolean) => {
      update({ kind: 'confirming', sessionId, report });
      try {
        await instanceArchiveService.confirmImport(sessionId, acknowledgeExecutables);
        update({ kind: 'queued' });
        onQueued();
      } catch (error) {
        update({ kind: 'review', sessionId, report, errorCode: archiveErrorCode(error) });
      }
    },
    [onQueued, update],
  );

  const cancel = useCallback(
    async (sessionId?: string) => {
      abort.current?.abort();
      if (sessionId) {
        await instanceArchiveService.cancelImport(sessionId).catch(() => undefined);
      }
      update({ kind: 'idle' });
    },
    [update],
  );

  return { phase, upload, stage, confirm, cancel };
}
