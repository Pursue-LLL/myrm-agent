/**
 * [INPUT]
 * localStorage `developer_show_system_messages` and window event `developer-mode-changed`
 * (POS: Browser-side persistence and same-tab announcement of the developer-mode switch)
 *
 * [OUTPUT]
 * useShowSystemMessages: Whether developer mode currently shows system-role messages in the chat
 * setShowSystemMessages: Turns the switch on or off, persists it and makes every reader render again
 *
 * [POS]
 * Single owner of the developer-mode switch for message rows. It keeps no copy of the value: every render
 * reads the persisted switch, and the announcement event only tells React to read it again.
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

export function setShowSystemMessages(enabled: boolean): void {
  localStorage.setItem(SWITCH_STORAGE_KEY, String(enabled));
  window.dispatchEvent(new Event(SWITCH_CHANGED_EVENT));
}
