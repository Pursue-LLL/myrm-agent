import { parseUserAgentFetchErrorMessage } from './agentFetchErrorCore';
import { riskHeldErrorFromResponse } from './riskHeldToast';

/** Throws the most specific error a failed user-agents response carries. */
export async function throwUserAgentFetchError(response: Response, action: string): Promise<never> {
  const riskHeld = await riskHeldErrorFromResponse(response);
  if (riskHeld) {
    throw riskHeld;
  }
  const errorText = await response.text();
  throw new Error(parseUserAgentFetchErrorMessage(errorText, action, response.statusText));
}
