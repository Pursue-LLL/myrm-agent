'use client';

import { useCallback, useEffect, useState } from 'react';

import { isLocalMode } from '@/lib/deploy-mode';
import { systemService, type TunnelStatus } from '@/services/system';
import useConfigStore from '@/store/useConfigStore';

const IDLE_STATUS: TunnelStatus = {
  running: false,
  url: null,
  target_port: null,
  ingress_synced: false,
};

const STATUS_POLL_MS = 10_000;

export function useTunnel(webuiPort: number, passwordProtectionEnabled: boolean) {
  const setPublicIngressBaseUrl = useConfigStore((s) => s.setPublicIngressBaseUrl);
  const [status, setStatus] = useState<TunnelStatus>(IDLE_STATUS);
  const [starting, setStarting] = useState(false);

  const syncIngressFromServer = useCallback(async () => {
    try {
      const ingressUrl = await systemService.getIngressUrl();
      setPublicIngressBaseUrl(ingressUrl || undefined);
    } catch {
      // Ingress resolver may be empty when tunnel is off; keep current store value.
    }
  }, [setPublicIngressBaseUrl]);

  const refreshStatus = useCallback(async () => {
    if (!isLocalMode()) {
      setStatus(IDLE_STATUS);
      return;
    }
    try {
      const next = await systemService.getTunnelStatus();
      setStatus(next);
      await syncIngressFromServer();
    } catch {
      setStatus(IDLE_STATUS);
    }
  }, [syncIngressFromServer]);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  useEffect(() => {
    if (!isLocalMode() || (!status.running && !starting)) {
      return;
    }
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, STATUS_POLL_MS);
    return () => window.clearInterval(timer);
  }, [refreshStatus, starting, status.running]);

  const start = useCallback(async () => {
    if (!passwordProtectionEnabled) {
      throw new Error('Password protection must be enabled before starting a public tunnel.');
    }
    setStarting(true);
    try {
      const next = await systemService.startTunnel(webuiPort, passwordProtectionEnabled);
      setStatus(next);
      await syncIngressFromServer();
      return next;
    } finally {
      setStarting(false);
    }
  }, [passwordProtectionEnabled, syncIngressFromServer, webuiPort]);

  const stop = useCallback(async () => {
    const next = await systemService.stopTunnel();
    setStatus(next);
    await syncIngressFromServer();
    return next;
  }, [syncIngressFromServer]);

  return {
    status,
    starting,
    refreshStatus,
    start,
    stop,
  };
}
