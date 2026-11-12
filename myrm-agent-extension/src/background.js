/**
 * Myrm Agent Extension — Background Service Worker (MV3) entry.
 *
 * [INPUT]
 * - background/*.js (POS: the service worker's modules; importing a listener module arms its listeners)
 *
 * [OUTPUT]
 * - (none; the manifest's service_worker entry)
 *
 * [POS] Lifecycle only: restore the saved settings and connect on install and browser start, and reconnect on the
 * keep-alive alarm. Everything else lives in src/background/.
 */

import "./background/tab_events.js";
import "./background/ui_messages.js";
import { connect } from "./background/connection.js";
import { setupContextMenu } from "./background/context_menu.js";
import { ALARM_NAME, restoreState, state } from "./background/state.js";

async function restoreAndConnect() {
  await restoreState();
  if (state.serverUrl) connect();
}

chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create(ALARM_NAME, { periodInMinutes: 0.4 });
  setupContextMenu();
  void restoreAndConnect();
});

chrome.runtime.onStartup.addListener(() => {
  setupContextMenu();
  void restoreAndConnect();
});

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME && !state.ws && state.serverUrl && !state.isConnecting) {
    connect();
  }
});
