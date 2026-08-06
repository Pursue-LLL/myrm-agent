/**
 * Wiki clip outcome notifications (success / duplicate / security / error).
 */

import { msg } from "../i18n.js";
import {
  resolveClipNotifyPayload,
  shouldStoreClipNotifyDeepLink,
} from "./clip_notify_payload.js";

const NOTIFY_ICON = "icons/icon128.png";
const SESSION_KEY_PREFIX = "clipNotify:";

let listenersReady = false;

function sessionKey(notificationId) {
  return `${SESSION_KEY_PREFIX}${notificationId}`;
}

async function storeOpenUrl(notificationId, openUrl) {
  if (!shouldStoreClipNotifyDeepLink(openUrl)) return;
  await chrome.storage.session.set({ [sessionKey(notificationId)]: openUrl });
}

async function takeOpenUrl(notificationId) {
  const key = sessionKey(notificationId);
  const stored = await chrome.storage.session.get(key);
  const openUrl = stored[key];
  if (openUrl) {
    await chrome.storage.session.remove(key);
  }
  return typeof openUrl === "string" ? openUrl : "";
}

function registerListeners() {
  if (listenersReady) return;
  listenersReady = true;

  chrome.notifications.onClicked.addListener(async (notificationId) => {
    if (!notificationId.startsWith("clip-")) return;
    const openUrl = await takeOpenUrl(notificationId);
    chrome.notifications.clear(notificationId);
    if (openUrl) {
      chrome.tabs.create({ url: openUrl }).catch(() => {});
    }
  });

  chrome.notifications.onClosed.addListener(async (notificationId) => {
    if (!notificationId.startsWith("clip-")) return;
    await takeOpenUrl(notificationId);
  });
}

/**
 * @param {"success" | "success_no_origin" | "duplicate" | "security" | "error"} kind
 * @param {{ openUrl?: string, errorMessage?: string }} [options]
 */
export async function notifyClipOutcome(kind, options = {}) {
  if (!chrome.notifications?.create) return;
  registerListeners();

  const { openUrl = "", errorMessage = "" } = options;
  const notificationId = `clip-${kind}-${Date.now()}`;
  const payload = resolveClipNotifyPayload(kind, { openUrl, errorMessage }, msg);

  if (shouldStoreClipNotifyDeepLink(openUrl)) {
    await storeOpenUrl(notificationId, openUrl);
  }

  chrome.notifications.create(
    notificationId,
    {
      type: "basic",
      iconUrl: NOTIFY_ICON,
      title: msg(payload.titleKey),
      message: payload.body,
    },
    (createdId) => {
      const err = chrome.runtime.lastError;
      if (err || !createdId) {
        void takeOpenUrl(notificationId);
      }
    },
  );
}
