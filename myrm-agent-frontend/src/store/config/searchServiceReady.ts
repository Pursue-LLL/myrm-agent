/**
 * [INPUT]
 * @/lib/deploy-mode::isLocalMode (POS: local vs cloud deploy mode)
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
import { isLocalMode } from '@/lib/deploy-mode';
import { withTimeout } from '@/lib/utils/withTimeout';
import { getConfigSyncManager } from '@/services/config';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from './searchService';

/** The longest the gate stays silent while it waits for the account's search services. */
const SEARCH_SERVICES_WAIT_MS = 3000;

/**
 * Cloud start-up returns the first screen's keys and loads the rest in the background, once and without a retry, so
 * the list is empty while that load is in flight and for good once it failed. An empty list the server has not
 * confirmed is not "no search service": the gate asks for the key first, decides on the list once the server has
 * answered (a refusal shows the setup notice), and lets the turn through when the answer fails or takes longer than
 * the wait limit, because the server refuses a turn without a search service anyway. Local mode returns every key with
 * the first request, so there is nothing to wait for (the wait would instead block on the local backend becoming
 * ready).
 *
 * Resolves whether the turn may go on; false means it was refused here and the notice has been shown.
 */
export const checkSearchServiceReady = async (): Promise<boolean> => {
  if (!isLocalMode()) {
    const known = await withTimeout(
      getConfigSyncManager().ensureKeyLoaded('searchServices'),
      SEARCH_SERVICES_WAIT_MS,
    ).catch(() => false);
    if (!known) {
      return true;
    }
  }
  return guardSearchServiceConfigured(useConfigStore.getState().searchServiceConfigs);
};
