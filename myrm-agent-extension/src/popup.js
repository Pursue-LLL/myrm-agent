/**
 * Myrm Agent Extension — Popup UI Controller
 *
 * Manages the popup interface for configuring server connection,
 * authorized domains, and viewing connection status.
 */

import { applyDocumentI18n, msg } from "./i18n.js";

const serverUrlInput = document.getElementById("server-url");
const authTokenInput = document.getElementById("auth-token");
const domainsTextarea = document.getElementById("domains");
const allowAllCheckbox = document.getElementById("allow-all-tabs");
const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const btnApplyPairing = document.getElementById("btn-apply-pairing");
const pairingCodeInput = document.getElementById("pairing-code");
const statusBadge = document.getElementById("status-badge");
const statusText = document.getElementById("status-text");
const errorHint = document.getElementById("error-hint");
const errorLinkWrap = document.getElementById("error-link-wrap");
const errorLink = document.getElementById("error-link");
const clipSuccessHint = document.getElementById("clip-success-hint");
const clipTargetRow = document.getElementById("clip-target-row");
const clipTargetLabel = document.getElementById("clip-target-label");
const tabsSection = document.getElementById("tabs-section");
const tabsList = document.getElementById("tabs-list");

applyDocumentI18n();
document.title = msg("extName");

function readPausedTabIds(callback) {
  chrome.storage.local.get(["pausedTabIds"], (data) => {
    const pausedTabIds = Array.isArray(data.pausedTabIds)
      ? data.pausedTabIds.filter((id) => Number.isInteger(id))
      : [];
    callback(pausedTabIds);
  });
}

function pushAccessPolicyToBackground() {
  const domains = domainsTextarea.value
    .split("\n")
    .map((d) => d.trim())
    .filter(Boolean);
  const allowAllEligibleTabs = Boolean(allowAllCheckbox?.checked);
  readPausedTabIds((pausedTabIds) => {
    chrome.storage.local.set({ authorizedDomains: domains, allowAllEligibleTabs, pausedTabIds });
    chrome.runtime.sendMessage({
      type: "update_access_policy",
      domains,
      allowAllEligibleTabs,
      pausedTabIds,
    });
  });
}

function connectWithCurrentSettings() {
  const serverUrl = serverUrlInput.value.trim();
  const authToken = authTokenInput.value.trim();
  const domains = domainsTextarea.value
    .split("\n")
    .map((d) => d.trim())
    .filter(Boolean);
  const allowAllEligibleTabs = Boolean(allowAllCheckbox?.checked);

  if (!serverUrl) {
    serverUrlInput.style.borderColor = "#ef4444";
    return false;
  }

  chrome.storage.local.set({
    serverUrl,
    authToken,
    authorizedDomains: domains,
    allowAllEligibleTabs,
    pairingHttpBase: "",
  });

  chrome.runtime.sendMessage({
    type: "connect",
    serverUrl,
    authToken,
  });

  readPausedTabIds((pausedTabIds) => {
    chrome.runtime.sendMessage({
      type: "update_access_policy",
      domains,
      allowAllEligibleTabs,
      pausedTabIds,
    });
  });

  return true;
}

// Load saved settings
chrome.storage.local.get(["serverUrl", "authToken", "authorizedDomains", "allowAllEligibleTabs"], (data) => {
  serverUrlInput.value = data.serverUrl || "";
  authTokenInput.value = data.authToken || "";
  domainsTextarea.value = (data.authorizedDomains || []).join("\n");
  if (allowAllCheckbox) {
    allowAllCheckbox.checked = data.allowAllEligibleTabs === true;
  }
  refreshStatus();
});

function refreshStatus() {
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    if (!response) return;

    const { connected, connecting, lastError, lastClipErrorKind } = response;
    let state = "disconnected";
    let labelKey = "statusDisconnected";
    if (connected) {
      state = "connected";
      labelKey = "statusConnected";
    } else if (connecting) {
      state = "connecting";
      labelKey = "statusConnecting";
    }

    statusBadge.className = `status-badge ${state}`;
    statusText.textContent = msg(labelKey);
    btnConnect.style.display = connected || connecting ? "none" : "block";
    btnDisconnect.style.display = connected ? "block" : "none";

    if (lastError) {
      if (clipSuccessHint) clipSuccessHint.style.display = "none";
      errorHint.textContent = lastError;
      errorHint.style.display = "block";
      const reviewUrl = response.duplicateReviewUrl || "";
      const ignoreUrl = response.wikiIgnoreUrl || "";
      if (lastClipErrorKind === "duplicate" && reviewUrl) {
        errorLink.href = reviewUrl;
        errorLink.textContent = msg("openDuplicateReview");
        errorLinkWrap.style.display = "block";
      } else if (lastClipErrorKind === "security" && ignoreUrl) {
        errorLink.href = ignoreUrl;
        errorLink.textContent = msg("openWikiIgnoreRules");
        errorLinkWrap.style.display = "block";
      } else {
        errorLinkWrap.style.display = "none";
      }
    } else if (response.clipSuccessUrl) {
      if (clipSuccessHint) clipSuccessHint.style.display = "none";
      errorHint.textContent = "";
      errorHint.style.display = "none";
      errorLink.href = response.clipSuccessUrl;
      errorLink.textContent = msg("openClippedRaw");
      errorLinkWrap.style.display = "block";
    } else if (response.clipSavedWithoutOrigin && clipSuccessHint) {
      errorHint.textContent = "";
      errorHint.style.display = "none";
      errorLinkWrap.style.display = "none";
      clipSuccessHint.textContent = msg("clipSavedWithoutOrigin");
      clipSuccessHint.style.display = "block";
    } else {
      if (clipSuccessHint) clipSuccessHint.style.display = "none";
      errorHint.textContent = "";
      errorHint.style.display = "none";
      errorLinkWrap.style.display = "none";
    }

    const clipLabel = response.clipAgentId?.trim() || msg("defaultAgent");
    if (clipTargetRow && clipTargetLabel) {
      clipTargetLabel.textContent = clipLabel;
      clipTargetRow.style.display = "block";
    }

    if (connected && response.attachedTabs && response.attachedTabs.length > 0) {
      tabsSection.style.display = "block";
      tabsList.innerHTML = response.attachedTabs
        .map((id) => `<div class="tab-item"><span class="domain">${msg("tabItemLabel", id)}</span></div>`)
        .join("");
    } else {
      tabsSection.style.display = "none";
      tabsList.innerHTML = "";
    }
  });
}

btnConnect.addEventListener("click", () => {
  if (connectWithCurrentSettings()) {
    setTimeout(refreshStatus, 1000);
  }
});

btnDisconnect.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" });
  setTimeout(refreshStatus, 500);
});

function resolveHttpBaseFromWsUrl(wsUrl) {
  const trimmed = (wsUrl || "").trim();
  if (!trimmed) return "";
  return trimmed
    .replace(/^wss:\/\//i, "https://")
    .replace(/^ws:\/\//i, "http://")
    .replace(/\/api\/v1\/ws\/extension.*$/i, "");
}

function parsePairingInput(raw) {
  const trimmed = (raw || "").trim();
  if (!trimmed) {
    return { code: "", httpBase: "" };
  }

  if (trimmed.startsWith("{")) {
    try {
      const bundle = JSON.parse(trimmed);
      const httpBase = String(bundle.http_base || bundle.httpBase || bundle.base || "").replace(/\/$/, "");
      const code = String(bundle.code || "").trim();
      return { code, httpBase };
    } catch {
      return { code: trimmed, httpBase: "" };
    }
  }

  if (/^https?:\/\//i.test(trimmed)) {
    try {
      const url = new URL(trimmed);
      const segments = url.pathname.split("/").filter(Boolean);
      const code = decodeURIComponent(segments[segments.length - 1] || "");
      return { code, httpBase: url.origin };
    } catch {
      return { code: trimmed, httpBase: "" };
    }
  }

  if (trimmed.includes("\n")) {
    const [first, second] = trimmed.split("\n").map((part) => part.trim());
    if (/^https?:\/\//i.test(first)) {
      return { httpBase: first.replace(/\/$/, ""), code: second };
    }
  }

  return { code: trimmed, httpBase: "" };
}

btnApplyPairing.addEventListener("click", async () => {
  const parsed = parsePairingInput(pairingCodeInput?.value || "");
  if (!parsed.code) return;

  const stored = await chrome.storage.local.get(["pairingHttpBase", "serverUrl"]);
  const httpBase =
    parsed.httpBase ||
    stored.pairingHttpBase ||
    resolveHttpBaseFromWsUrl(stored.serverUrl || serverUrlInput.value.trim());

  if (!httpBase) {
    errorHint.textContent = msg("errPairingNeedsBundle");
    errorHint.style.display = "block";
    return;
  }

  try {
    const resp = await fetch(`${httpBase.replace(/\/$/, "")}/api/v1/extension/pairing/consume`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: parsed.code }),
    });
    if (!resp.ok) throw new Error("pairing failed");
    const data = await resp.json();
    serverUrlInput.value = data.ws_url || "";
    authTokenInput.value = data.auth_token || "";
    await chrome.storage.local.set({
      serverUrl: serverUrlInput.value,
      authToken: authTokenInput.value,
      pairingHttpBase: data.http_base || httpBase,
    });
    pairingCodeInput.value = "";
    errorHint.style.display = "none";
    if (connectWithCurrentSettings()) {
      setTimeout(refreshStatus, 1000);
    }
  } catch {
    errorHint.textContent = msg("errPairingInvalid");
    errorHint.style.display = "block";
  }
});

// Auto-save domains on change
domainsTextarea.addEventListener("change", () => {
  pushAccessPolicyToBackground();
});

allowAllCheckbox?.addEventListener("change", () => {
  pushAccessPolicyToBackground();
});

// Refresh status periodically while popup is open
setInterval(refreshStatus, 2000);
