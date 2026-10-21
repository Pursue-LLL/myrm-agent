'use client';

import { useCallback, useEffect, useState } from 'react';
import { systemService, type IngressRequirementSnapshot } from '@/services/system';

const EMPTY_SNAPSHOT: IngressRequirementSnapshot = {
  required: false,
  has_public_ingress: false,
  reasons: [],
  channels: {},
};

export function useIngressRequirement(): IngressRequirementSnapshot | null {
  const [snapshot, setSnapshot] = useState<IngressRequirementSnapshot | null>(null);

  const evaluate = useCallback(async (cancelled: () => boolean) => {
    try {
      const data = await systemService.getIngressRequirement();
      if (!cancelled()) {
        setSnapshot(data);
      }
    } catch {
      if (!cancelled()) {
        setSnapshot(EMPTY_SNAPSHOT);
      }
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    const cancelled = () => disposed;
    void evaluate(cancelled);
    return () => {
      disposed = true;
    };
  }, [evaluate]);

  useEffect(() => {
    let disposed = false;
    const cancelled = () => disposed;
    const refresh = () => {
      void evaluate(cancelled);
    };
    window.addEventListener('channel-credentials-saved', refresh);
    window.addEventListener('cron_updated', refresh);
    window.addEventListener('ingress-requirement-changed', refresh);
    return () => {
      disposed = true;
      window.removeEventListener('channel-credentials-saved', refresh);
      window.removeEventListener('cron_updated', refresh);
      window.removeEventListener('ingress-requirement-changed', refresh);
    };
  }, [evaluate]);

  return snapshot;
}
