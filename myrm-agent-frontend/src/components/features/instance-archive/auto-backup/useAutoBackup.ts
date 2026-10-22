'use client';

/**
 * [INPUT]
 * - @/services/instanceAutoBackup::instanceAutoBackupService (POS: scheduled backup HTTP client)
 * - @/services/instanceArchive::archiveErrorCode (POS: stable reason of a failed call)
 *
 * [OUTPUT]
 * - useAutoBackup: schedule + last outcome, with save / back-up-now actions and live progress
 *
 * [POS]
 * Single source of truth for the "Automatic backup" card. While a backup is running it polls
 * until the server reports it finished, so the card shows the real result instead of a guess.
 */

import { useCallback, useEffect, useState } from 'react';
import { archiveErrorCode } from '@/services/instanceArchive';
import { instanceAutoBackupService, type AutoBackup, type AutoBackupSettings } from '@/services/instanceAutoBackup';

const POLL_MS = 2000;

interface UseAutoBackupResult {
  /** `null` until the first successful read (or when the endpoint is not reachable for this identity). */
  data: AutoBackup | null;
  /** Stable reason of the last failed save or start; cleared by the next action. */
  errorCode: string | null;
  busy: boolean;
  update: (settings: AutoBackupSettings) => Promise<boolean>;
  runNow: () => Promise<void>;
}

export function useAutoBackup(): UseAutoBackupResult {
  const [data, setData] = useState<AutoBackup | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    try {
      setData(await instanceAutoBackupService.get());
    } catch {
      // Keep what is shown: a poll can fail while the backend restarts.
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const running = data?.running ?? false;
  useEffect(() => {
    if (!running) {
      return undefined;
    }
    const timer = setInterval(() => void reload(), POLL_MS);
    return () => clearInterval(timer);
  }, [running, reload]);

  const perform = useCallback(async (action: () => Promise<AutoBackup>): Promise<boolean> => {
    setBusy(true);
    setErrorCode(null);
    try {
      setData(await action());
      return true;
    } catch (error) {
      setErrorCode(archiveErrorCode(error));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const update = useCallback(
    (settings: AutoBackupSettings) => perform(() => instanceAutoBackupService.update(settings)),
    [perform],
  );
  const runNow = useCallback(async () => {
    await perform(() => instanceAutoBackupService.runNow());
  }, [perform]);

  return { data, errorCode, busy, update, runNow };
}
