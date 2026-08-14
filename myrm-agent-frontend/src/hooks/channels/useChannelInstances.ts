'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  createChannelInstance,
  deleteChannelInstance,
  listChannelInstances,
  updateChannelDisplayName,
  type ChannelInstance,
} from '@/services/channels';

interface UseChannelInstancesOptions {
  /** Channel type to manage (e.g. "feishu"). */
  channelType: string;
  /** Default instance name that represents the primary account. */
  primaryName: string;
  /** i18n prefix for toast messages (e.g. "feishu"). */
  i18nPrefix: string;
  /** Optional callback invoked after an instance is added/removed/renamed. */
  onChange?: () => void;
}

interface UseChannelInstancesResult {
  instances: ChannelInstance[];
  /** Extra instances excluding the primary one. */
  extraInstances: ChannelInstance[];
  loading: boolean;
  adding: boolean;
  refresh: () => Promise<void>;
  addInstance: (displayName?: string, credentials?: Record<string, string>) => Promise<ChannelInstance | null>;
  removeInstance: (instanceId: string) => Promise<boolean>;
  renameInstance: (channelName: string, displayName: string) => Promise<void>;
}

export function useChannelInstances(options: UseChannelInstancesOptions): UseChannelInstancesResult {
  const t = useTranslations('channels');
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const [instances, setInstances] = useState<ChannelInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const all = await listChannelInstances(optionsRef.current.channelType);
      setInstances(all);
    } catch {
      setInstances([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addInstance = useCallback(
    async (displayName?: string, credentials?: Record<string, string>): Promise<ChannelInstance | null> => {
      const { channelType, i18nPrefix } = optionsRef.current;
      setAdding(true);
      try {
        const inst = await createChannelInstance(channelType, displayName, credentials);
        setInstances((prev) => [...prev, inst]);
        toast.success(t(`${i18nPrefix}InstanceAdded`));
        optionsRef.current.onChange?.();
        return inst;
      } catch (error) {
        const message = error instanceof Error ? error.message : t(`${i18nPrefix}InstanceAddError`);
        toast.error(message);
        return null;
      } finally {
        setAdding(false);
      }
    },
    [t],
  );

  const removeInstance = useCallback(
    async (instanceId: string): Promise<boolean> => {
      const { i18nPrefix } = optionsRef.current;
      try {
        await deleteChannelInstance(instanceId);
        setInstances((prev) => prev.filter((i) => i.instanceId !== instanceId));
        toast.success(t(`${i18nPrefix}InstanceRemoved`));
        optionsRef.current.onChange?.();
        return true;
      } catch {
        toast.error(t(`${i18nPrefix}InstanceRemoveError`));
        return false;
      }
    },
    [t],
  );

  const renameInstance = useCallback(
    async (channelName: string, displayName: string) => {
      const { i18nPrefix } = optionsRef.current;
      try {
        const updated = await updateChannelDisplayName(channelName, displayName);
        setInstances((prev) =>
          prev.map((i) => (i.channelName === channelName ? { ...i, displayName: updated.displayName } : i)),
        );
        optionsRef.current.onChange?.();
      } catch {
        toast.error(t(`${i18nPrefix}LabelSaveError`));
      }
    },
    [t],
  );

  const primaryName = optionsRef.current.primaryName;
  return {
    instances,
    extraInstances: instances.filter((i) => i.channelName !== primaryName),
    loading,
    adding,
    refresh,
    addInstance,
    removeInstance,
    renameInstance,
  };
}
