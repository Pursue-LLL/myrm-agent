/**
 * [INPUT]
 * @/store/useProviderStore (POS: provider config SSOT; every change made here persists through it)
 * ./providerTypes::ProviderConfig (POS: provider state shape)
 *
 * [OUTPUT]
 * enableProviderWithModel: enables a provider with one model and fills an empty base-model slot
 *
 * [POS]
 * The rule every one-click connect shares: the provider starts working with the model it was connected for, whatever
 * the user chose before stays, and the default model is only ever filled in, never replaced.
 */

import useProviderStore from '@/store/useProviderStore';
import type { ProviderConfig } from './providerTypes';

/**
 * Enables the provider with `model` and fills an empty base-model slot. Models the provider already had stay enabled
 * and an occupied base slot is left alone. `extra` carries provider fields the connect itself decided, such as the
 * address the model was found at.
 */
export function enableProviderWithModel(
  providerId: string,
  model: string,
  extra: Partial<Pick<ProviderConfig, 'apiUrl'>> = {},
): void {
  const store = useProviderStore.getState();
  const provider = store.providers.find((p) => p.id === providerId);
  if (!provider) {
    return;
  }

  const update: Partial<ProviderConfig> = { ...extra, isEnabled: true };
  if (!provider.enabledModels.includes(model)) {
    update.availableModels = Array.from(new Set([...provider.availableModels, model]));
    update.enabledModels = [...provider.enabledModels, model];
  }
  store.updateProvider(providerId, update);

  if (!store.defaultModelConfig.baseModel.primary) {
    store.setBaseModel({ providerId, model });
  }
}
