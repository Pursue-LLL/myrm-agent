import { useEffect, useRef } from 'react';
import type { ProviderConfig, SingleModelSelection } from '@/store/config/providerTypes';
import useProviderStore from '@/store/useProviderStore';
import { MODEL_SLOTS } from './modelSlots';

/** A saved selection is usable while its provider exists, is enabled, holds an active key and lists the model. */
export function isSelectionUsable(providers: ProviderConfig[], selection: SingleModelSelection | null): boolean {
  if (!selection) {
    return true;
  }
  const provider = providers.find((p) => p.id === selection.providerId);
  return Boolean(
    provider?.isEnabled &&
    provider.apiKeys.some((key) => key.isActive && key.key) &&
    provider.enabledModels.includes(selection.model),
  );
}

/** Once the provider config has loaded, clears each saved model selection that can no longer be used. Runs once. */
export function useClearInvalidModelSelections(isInitialized: boolean): void {
  const hasCleared = useRef(false);

  useEffect(() => {
    if (!isInitialized || hasCleared.current) {
      return;
    }
    const state = useProviderStore.getState();
    for (const { read, write } of Object.values(MODEL_SLOTS)) {
      if (!isSelectionUsable(state.providers, read(state.defaultModelConfig) ?? null)) {
        write(state)(null);
      }
    }
    hasCleared.current = true;
  }, [isInitialized]);
}
