/**
 * Myrm Agent Extension — Background Service Worker (MV3) entry.
 *
 * [INPUT]
 * - background/*.js (POS: the service worker's modules; importing a listener module arms its listeners)
 *
 * [OUTPUT]
 * - (none; the manifest's service_worker entry)
 *
 * [POS] Lifecycle only. The browser stops this worker whenever it likes and starts a fresh one with empty memory, so
 * every start (install, browser start, an alarm, a message) runs the same recovery: load the saved settings, release
 * what the previous worker left attached, make sure the keep-alive alarm exists and reconnect unless the user
 * disconnected on purpose. Everything else lives in src/background/.
 */

import "./background/tab_events.js";
import "./background/ui_messages.js";
import { pruneAgentTabs } from "./background/agent_tabs.js";
import { reconnectIfWanted } from "./background/connection.js";
import { setupContextMenu } from "./background/context_menu.js";
import { releaseStaleDebuggers } from "./background/debugger.js";
import { ALARM_NAME, KEEP_ALIVE_PERIOD_MINUTES, whenRestored } from "./background/state.js";

async function ensureKeepAliveAlarm() {
  // Creating an alarm again restarts its schedule, so an existing one is left alone.
  if (!(await chrome.alarms.get(ALARM_NAME))) {
    await chrome.alarms.create(ALARM_NAME, { periodInMinutes: KEEP_ALIVE_PERIOD_MINUTES });
  }
}

async function recover() {
  await whenRestored();
  const steps = await Promise.allSettled([releaseStaleDebuggers(), pruneAgentTabs(), ensureKeepAliveAlarm()]);
  for (const step of steps) {
    // A failed step must not keep the extension offline; it only costs what that step protects.
    if (step.status === "rejected") console.warn("[Myrm] Start-up step failed:", step.reason);
  }
  reconnectIfWanted();
}

const recovered = recover();

chrome.runtime.onInstalled.addListener(setupContextMenu);
chrome.runtime.onStartup.addListener(setupContextMenu);

chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === ALARM_NAME) void recovered.then(reconnectIfWanted);
});
