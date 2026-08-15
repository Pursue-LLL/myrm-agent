'use client';

import { create } from 'zustand';
import type { ChannelInstance } from '@/services/channels';

interface ChannelInstancesState {
  /** Instance lists keyed by channel type, shared across every mounted config card. */
  instancesByType: Record<string, ChannelInstance[]>;
  /** Replace the instance list for a channel type. */
  setInstancesForType: (channelType: string, instances: ChannelInstance[]) => void;
  /** Apply a functional update to the instance list for a channel type. */
  updateInstancesForType: (channelType: string, updater: (prev: ChannelInstance[]) => ChannelInstance[]) => void;
}

/**
 * Shared channel-instance state.
 *
 * The channels settings screen mounts the same config card twice on desktop
 * (the right-hand panel plus the responsive in-list detail). Each card runs
 * `useChannelInstances`; keeping the list in this store guarantees a delete in
 * one card is reflected in the other, instead of leaving a stale card behind.
 */
export const useChannelInstancesStore = create<ChannelInstancesState>((set) => ({
  instancesByType: {},
  setInstancesForType: (channelType, instances) =>
    set((state) => ({
      instancesByType: { ...state.instancesByType, [channelType]: instances },
    })),
  updateInstancesForType: (channelType, updater) =>
    set((state) => ({
      instancesByType: {
        ...state.instancesByType,
        [channelType]: updater(state.instancesByType[channelType] ?? []),
      },
    })),
}));
