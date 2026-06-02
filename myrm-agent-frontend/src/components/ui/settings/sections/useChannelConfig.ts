'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import type { ConnectionStatus } from './ConnectionBadge';
import { useConnectionStatusLabel } from './useConnectionStatusLabel';

interface ChannelConfigOptions<T extends object> {
  emptyCreds: T;
  requiredFields: (keyof T)[];
  getCreds: () => Promise<T | null>;
  saveCreds: (creds: T) => Promise<void>;
  testConnection: (creds: T) => Promise<{ ok: boolean; message?: string }>;
  i18nPrefix: string;
}

interface ChannelConfigResult<T extends object> {
  creds: T;
  dirty: boolean;
  loading: boolean;
  saving: boolean;
  testing: boolean;
  connStatus: ConnectionStatus;
  statusLabel: string;
  handleChange: (field: keyof T, value: T[keyof T]) => void;
  handleSave: () => Promise<void>;
  handleTest: () => Promise<void>;
  refreshCreds: () => Promise<void>;
}

export function useChannelConfig<T extends object>(options: ChannelConfigOptions<T>): ChannelConfigResult<T> {
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const t = useTranslations('channels');

  const [creds, setCreds] = useState<T>(options.emptyCreds);
  const savedCredsRef = useRef<string>(JSON.stringify(options.emptyCreds));
  const [dirty, setDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connStatus, setConnStatus] = useState<ConnectionStatus>('unchecked');

  const isConfigured = useCallback(
    (c: T): boolean => optionsRef.current.requiredFields.every((f) => Boolean(c[f])),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    async function init() {
      const { getCreds, testConnection } = optionsRef.current;
      try {
        const raw = await getCreds();
        if (cancelled) return;
        const saved = raw ? { ...optionsRef.current.emptyCreds, ...raw } : null;
        if (!saved || !isConfigured(saved)) {
          if (saved) {
            setCreds(saved);
            savedCredsRef.current = JSON.stringify(saved);
          }
          setConnStatus('unconfigured');
          return;
        }
        setCreds(saved);
        savedCredsRef.current = JSON.stringify(saved);
        setConnStatus('checking');
        const result = await testConnection(saved);
        if (!cancelled) setConnStatus(result.ok ? 'connected' : 'error');
      } catch {
        if (!cancelled) setConnStatus('unconfigured');
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    init();
    return () => {
      cancelled = true;
    };
  }, [isConfigured]);

  const handleChange = useCallback((field: keyof T, value: T[keyof T]) => {
    setCreds((prev) => {
      const next = { ...prev, [field]: value };
      setDirty(JSON.stringify(next) !== savedCredsRef.current);
      return next;
    });
    setConnStatus('unchecked');
  }, []);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await optionsRef.current.saveCreds(creds);
      savedCredsRef.current = JSON.stringify(creds);
      setDirty(false);
      toast.success(t(`${optionsRef.current.i18nPrefix}Saved`));
      window.dispatchEvent(new CustomEvent('channel-credentials-saved'));

      if (isConfigured(creds)) {
        setTesting(true);
        setConnStatus('checking');
        try {
          const result = await optionsRef.current.testConnection(creds);
          setConnStatus(result.ok ? 'connected' : 'error');
          if (result.ok) toast.success(t(`${optionsRef.current.i18nPrefix}TestSuccess`));
          else toast.error(result.message || t(`${optionsRef.current.i18nPrefix}TestFailed`));
        } catch {
          setConnStatus('error');
        } finally {
          setTesting(false);
        }
      }
    } catch {
      toast.error(t(`${optionsRef.current.i18nPrefix}SaveError`));
    } finally {
      setSaving(false);
    }
  }, [creds, isConfigured, t]);

  const handleTest = useCallback(async () => {
    if (!isConfigured(creds)) {
      toast.error(t(`${optionsRef.current.i18nPrefix}CredentialsRequired`));
      return;
    }
    setTesting(true);
    setConnStatus('checking');
    try {
      const result = await optionsRef.current.testConnection(creds);
      setConnStatus(result.ok ? 'connected' : 'error');
      if (result.ok) toast.success(t(`${optionsRef.current.i18nPrefix}TestSuccess`));
      else toast.error(result.message || t(`${optionsRef.current.i18nPrefix}TestFailed`));
    } catch {
      setConnStatus('error');
      toast.error(t(`${optionsRef.current.i18nPrefix}TestFailed`));
    } finally {
      setTesting(false);
    }
  }, [creds, isConfigured, t]);

  const refreshCreds = useCallback(async () => {
    try {
      const raw = await optionsRef.current.getCreds();
      const saved = raw ? { ...optionsRef.current.emptyCreds, ...raw } : null;
      if (saved) {
        setCreds(saved);
        savedCredsRef.current = JSON.stringify(saved);
        setDirty(false);
        if (isConfigured(saved)) {
          setConnStatus('checking');
          const result = await optionsRef.current.testConnection(saved);
          setConnStatus(result.ok ? 'connected' : 'error');
        }
      }
    } catch {
      /* best-effort refresh */
    }
  }, [isConfigured]);

  const statusLabel = useConnectionStatusLabel(connStatus);

  return {
    creds,
    dirty,
    loading,
    saving,
    testing,
    connStatus,
    statusLabel,
    handleChange,
    handleSave,
    handleTest,
    refreshCreds,
  };
}
