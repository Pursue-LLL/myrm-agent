/**
 * [INPUT]
 * @/lib/utils/withTimeout::withTimeout (POS: wait limit for a promise, rejecting on timeout)
 * @/services/config::getConfigSyncManager (POS: config sync manager, the write gateway of the synced configs)
 * @/store/useConfigStore (POS: Global config state manager)
 * ./searchService::guardSearchServiceConfigured (POS: setup notice for a turn that needs a search service)
 *
 * [OUTPUT]
 * checkSearchServiceReady: whether a turn that needs a search service may start, decided on the synced list
 *
 * [POS]
 * The one gate in front of every entry into the Quick Search mode (the send guard and the mode selector).
 */
import { withTimeout } from '@/lib/utils/withTimeout';
import { getConfigSyncManager } from '@/services/config';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from './searchService';

/** The longest the gate stays silent while it waits for the account's search services. */
const SEARCH_SERVICES_WAIT_MS = 3000;

/**
 * Brings the account's search services into the store; false while their state cannot be known: the request for the key
 * failed, or the manager has not reached the backend. A manager in that state holds nothing, and the local adapter
 * reports an unreachable backend like a missing row, so the store must not be loaded from it: it would keep the
 * defaults instead of the real configuration that arrives later.
 */
async function syncSearchServices(): Promise<boolean> {
  const manager = getConfigSyncManager();
  if (!(await manager.ensureKeyLoaded('searchServices')) || !manager.isInitialized) {
    return false;
  }
  await useConfigStore.getState().initConfig();
  return true;
}

/**
 * The store's list is empty until the configuration has arrived: cloud start-up returns the first screen's keys and
 * loads the rest in the background with at most three attempts, so the list is empty while that load is in flight and
 * stays empty when every attempt failed; a local start-up has it only once the backend is up. An empty list the server
 * has not confirmed is not "no search service": the gate waits for the key and the store to catch up, decides on the
 * list once they have (a refusal shows the setup notice), and lets the turn through when that fails or takes longer
 * than the wait limit, because the server refuses a turn without a search service anyway.
 *
 * Resolves whether the turn may go on; false means it was refused here and the notice has been shown.
 */
export const checkSearchServiceReady = async (): Promise<boolean> => {
  const known = await withTimeout(syncSearchServices(), SEARCH_SERVICES_WAIT_MS).catch(() => false);
  if (!known) {
    return true;
  }
  return guardSearchServiceConfigured(useConfigStore.getState().searchServiceConfigs);
};
