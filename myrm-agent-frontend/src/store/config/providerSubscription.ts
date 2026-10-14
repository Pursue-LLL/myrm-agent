/**
 * [INPUT]
 * @/store/useProviderStore (POS: provider config SSOT; every change made here persists through it)
 * @/services/models-dev::getModelsForProvider (POS: live model catalog)
 * ./subscriptionDefaultModel::pickSubscriptionDefaultModel (POS: catalog-driven starting model)
 * ./providerTypes::hasUsableProviderAuth (POS: whether a provider can still authenticate)
 *
 * [OUTPUT]
 * connectProviderSubscription, disconnectProviderSubscription
 *
 * [POS]
 * Store-side effects of a subscription (OAuth) login or logout. It is the one place where "connected" becomes provider
 * state, so the chat banner, the Models page and the Credentials page leave the app in the same condition.
 */

import { getModelsForProvider } from '@/services/models-dev';
import useProviderStore from '@/store/useProviderStore';
import { hasUsableProviderAuth, type ProviderConfig } from './providerTypes';
import { pickSubscriptionDefaultModel } from './subscriptionDefaultModel';

async function resolveStartingModel(providerId: string): Promise<string | null> {
  try {
    const { models } = await getModelsForProvider(providerId);
    return pickSubscriptionDefaultModel(models);
  } catch (error) {
    // Without the catalog the provider is still connected; the user picks models on the Models page.
    console.warn('[ProviderSubscription] Model catalog unavailable:', error);
    return null;
  }
}

/** Enables the provider with a model it can run, and fills an empty base-model slot. Existing choices stay untouched. */
async function applyStartingModel(providerId: string): Promise<void> {
  const startingModel = await resolveStartingModel(providerId);

  // The catalog request may have taken a while; decide on the state as it is now.
  const store = useProviderStore.getState();
  const provider = store.providers.find((p) => p.id === providerId);
  if (!provider) {
    return;
  }

  const hasChosenModels = provider.enabledModels.length > 0;
  const baseModel = hasChosenModels ? provider.enabledModels[0] : startingModel;
  if (!baseModel) {
    return;
  }

  const update: Partial<ProviderConfig> = { isEnabled: true };
  if (!hasChosenModels) {
    update.availableModels = Array.from(new Set([...provider.availableModels, baseModel]));
    update.enabledModels = [baseModel];
  }
  store.updateProvider(providerId, update);

  if (!store.defaultModelConfig.baseModel.primary) {
    store.setBaseModel({ providerId, model: baseModel });
  }
}

/**
 * Records a successful subscription login. The connected flag is set synchronously because it is already a fact; the
 * returned promise settles once the starting model has been applied, which needs the network.
 */
export async function connectProviderSubscription(providerId: string): Promise<void> {
  useProviderStore.getState().updateProvider(providerId, { oauthConnected: true });
  await applyStartingModel(providerId);
}

/**
 * Records a subscription logout. A provider that then has no other way to authenticate is disabled, which also frees
 * the model slots bound to it; one that still has an API key keeps working with it.
 */
export function disconnectProviderSubscription(providerId: string): void {
  const store = useProviderStore.getState();
  const provider = store.providers.find((p) => p.id === providerId);
  if (!provider) {
    return;
  }

  store.updateProvider(providerId, { oauthConnected: false });
  if (provider.isEnabled && !hasUsableProviderAuth({ ...provider, oauthConnected: false })) {
    store.setProviderEnabled(providerId, false);
  }
}
