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
import { useChannelInstancesStore } from './useChannelInstancesStore';

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

  const instances = useChannelInstancesStore((s) => s.instancesByType[options.channelType] ?? []);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);

  const updateInstances = useCallback((updater: (prev: ChannelInstance[]) => ChannelInstance[]) => {
    useChannelInstancesStore.getState().updateInstancesForType(optionsRef.current.channelType, updater);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const all = await listChannelInstances(optionsRef.current.channelType);
      updateInstances(() => all);
    } catch {
      updateInstances(() => []);
    } finally {
      setLoading(false);
    }
  }, [updateInstances]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const addInstance = useCallback(
    async (displayName?: string, credentials?: Record<string, string>): Promise<ChannelInstance | null> => {
      const { channelType, i18nPrefix } = optionsRef.current;
      setAdding(true);
      try {
        const inst = await createChannelInstance(channelType, displayName, credentials);
        updateInstances((prev) => [...prev, inst]);
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
    [t, updateInstances],
  );

  const removeInstance = useCallback(
    async (instanceId: string): Promise<boolean> => {
      const { i18nPrefix } = optionsRef.current;
      try {
        await deleteChannelInstance(instanceId);
        updateInstances((prev) => prev.filter((i) => i.instanceId !== instanceId));
        toast.success(t(`${i18nPrefix}InstanceRemoved`));
        optionsRef.current.onChange?.();
        return true;
      } catch (error) {
        toast.error(t(`${i18nPrefix}InstanceRemoveError`));
        // 向上抛出让 ConfirmDialog 捕获，保持对话框打开以便用户重试
        throw error;
      }
    },
    [t, updateInstances],
  );

  const renameInstance = useCallback(
    async (channelName: string, displayName: string) => {
      const { i18nPrefix } = optionsRef.current;
      try {
        const updated = await updateChannelDisplayName(channelName, displayName);
        updateInstances((prev) =>
          prev.map((i) => (i.channelName === channelName ? { ...i, displayName: updated.displayName } : i)),
        );
        optionsRef.current.onChange?.();
      } catch {
        toast.error(t(`${i18nPrefix}LabelSaveError`));
      }
    },
    [t, updateInstances],
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
