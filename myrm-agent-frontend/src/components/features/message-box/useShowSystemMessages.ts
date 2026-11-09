/**
 * [INPUT]
 * localStorage `developer_show_system_messages` and window event `developer-mode-changed`
 * (POS: Written and announced by settings/sections/system/DeveloperSection when the developer switch is toggled)
 *
 * [OUTPUT]
 * useShowSystemMessages: Whether developer mode currently shows system-role messages in the chat
 *
 * [POS]
 * Reader of the developer-mode switch for message rows. It keeps no copy of the value: every render reads the
 * persisted switch, and the announcement event only tells React to read it again.
 */

import { useSyncExternalStore } from 'react';

const SWITCH_STORAGE_KEY = 'developer_show_system_messages';
const SWITCH_CHANGED_EVENT = 'developer-mode-changed';

function subscribe(onChange: () => void): () => void {
  window.addEventListener(SWITCH_CHANGED_EVENT, onChange);
  return () => window.removeEventListener(SWITCH_CHANGED_EVENT, onChange);
}

function readSwitch(): boolean {
  return localStorage.getItem(SWITCH_STORAGE_KEY) === 'true';
}

// The server has no localStorage. Hydration starts from "hidden" and the stored value follows without a mismatch.
function readSwitchOnServer(): boolean {
  return false;
}

export function useShowSystemMessages(): boolean {
  return useSyncExternalStore(subscribe, readSwitch, readSwitchOnServer);
}
