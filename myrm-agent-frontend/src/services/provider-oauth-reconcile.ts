/**
 * [INPUT]
 * @/services/provider-oauth::fetchProviderOAuthStatus, getProviderOAuthProviderByProviderId (POS: server-side login state)
 * @/store/config/providerTypes::ProviderConfig (type only)
 *
 * [OUTPUT]
 * reconcileProviderOAuthFlags: corrects the stored `oauthConnected` flags that disagree with the server's login state
 *
 * [POS]
 * Aligns the stored `oauthConnected` flag of subscription providers with the server, which owns the tokens. The flag is
 * a UI-side copy: it goes stale when the login ends elsewhere (another device, an expired grant, a server reset).
 */

import { fetchProviderOAuthStatus, getProviderOAuthProviderByProviderId } from '@/services/provider-oauth';
import type { ProviderConfig } from '@/store/config/providerTypes';

type ApplyFlag = (providerId: string, update: Pick<ProviderConfig, 'oauthConnected'>) => void;

/**
 * Asks the server for the login state of every subscription provider in `providers` and corrects the flags that
 * differ. A provider whose request fails keeps its flag, because an unreachable server proves nothing about the login.
 *
 * Every answer is compared with the flag the provider had when its request was sent. An answer that is older than a
 * login or logout completed in the meantime therefore agrees with that snapshot and changes nothing.
 */
export async function reconcileProviderOAuthFlags(
  providers: readonly ProviderConfig[],
  applyFlag: ApplyFlag,
): Promise<void> {
  await Promise.all(
    providers.map(async (provider) => {
      const oauthProvider = getProviderOAuthProviderByProviderId(provider.id);
      if (!oauthProvider) {
        return;
      }
      const flagAtRequest = Boolean(provider.oauthConnected);
      try {
        const connected = Boolean((await fetchProviderOAuthStatus(oauthProvider)).connected);
        if (connected !== flagAtRequest) {
          applyFlag(provider.id, { oauthConnected: connected });
        }
      } catch {
        // Offline or signed out: nothing is known, so nothing changes.
      }
    }),
  );
}
