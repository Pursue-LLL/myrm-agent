/**
 * Side Panel approval reminder: a system notification when the user is not looking at the browser window.
 *
 * [INPUT]
 * - `chrome.storage.local` setting `approvalNotifyEnabled` (the popup checkbox; on unless explicitly turned off)
 * - The focus state of the panel's browser window and the panel's visibility
 *
 * [OUTPUT]
 * - APPROVAL_NOTIFY_KEY: the storage key of the setting
 * - shouldNotifyApproval: the decision (pure)
 * - notifyApprovalPending / clearApprovalNotification: raise and withdraw the notification
 *
 * [POS] The panel's SSE stream cannot outlive the panel, so only the panel can tell that an approval is pending; the
 * notification carries no command text (it cannot be answered from there), and a click brings the browser window back.
 */

import { msg } from "../i18n.js";

export const APPROVAL_NOTIFY_KEY = "approvalNotifyEnabled";

/** One id for every approval: a newer request replaces the notification of the previous one. */
const NOTIFICATION_ID = "approval-pending";
const NOTIFY_ICON = "icons/icon128.png";

let clickListenerReady = false;
/** Bumped by every raise and every withdraw, so a notification still being prepared is dropped once it is stale. */
let epoch = 0;

/**
 * @param {{ enabled: boolean, windowFocused: boolean, pageHidden: boolean }} state
 * @returns {boolean}
 */
export function shouldNotifyApproval({ enabled, windowFocused, pageHidden }) {
  return enabled && (pageHidden || !windowFocused);
}

function registerClickListener() {
  if (clickListenerReady) return;
  clickListenerReady = true;
  chrome.notifications.onClicked.addListener(async (notificationId) => {
    if (notificationId !== NOTIFICATION_ID) return;
    chrome.notifications.clear(notificationId);
    try {
      const { id } = await chrome.windows.getCurrent();
      await chrome.windows.update(id, { focused: true });
    } catch (error) {
      console.warn("Could not bring the browser window forward", error);
    }
  });
}

/**
 * @param {string} deadlineText the localized "answer before" sentence, or "" when the request has no deadline
 * @returns {Promise<void>}
 */
export async function notifyApprovalPending(deadlineText) {
  if (!chrome.notifications?.create) return;
  const ticket = ++epoch;
  try {
    const [stored, browserWindow] = await Promise.all([
      chrome.storage.local.get(APPROVAL_NOTIFY_KEY),
      chrome.windows.getCurrent(),
    ]);
    const enabled = stored[APPROVAL_NOTIFY_KEY] !== false;
    const state = { enabled, windowFocused: browserWindow.focused, pageHidden: document.hidden };
    if (ticket !== epoch || !shouldNotifyApproval(state)) return;
    registerClickListener();
    await chrome.notifications.create(NOTIFICATION_ID, {
      type: "basic",
      iconUrl: chrome.runtime.getURL(NOTIFY_ICON),
      title: msg("notifyApprovalTitle"),
      message: [msg("notifyApprovalBody"), deadlineText].filter(Boolean).join("\n"),
    });
    if (ticket !== epoch) chrome.notifications.clear(NOTIFICATION_ID);
  } catch (error) {
    console.warn("Could not raise the approval notification", error);
  }
}

export function clearApprovalNotification() {
  epoch += 1;
  chrome.notifications?.clear?.(NOTIFICATION_ID);
}
