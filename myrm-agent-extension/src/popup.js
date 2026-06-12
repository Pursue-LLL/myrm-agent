/**
 * Myrm Agent Extension — Popup UI Controller
 *
 * Manages the popup interface for configuring server connection,
 * authorized domains, and viewing connection status.
 */

const serverUrlInput = document.getElementById("server-url");
const authTokenInput = document.getElementById("auth-token");
const domainsTextarea = document.getElementById("domains");
const btnConnect = document.getElementById("btn-connect");
const btnDisconnect = document.getElementById("btn-disconnect");
const statusBadge = document.getElementById("status-badge");
const statusText = document.getElementById("status-text");
const errorHint = document.getElementById("error-hint");
const tabsSection = document.getElementById("tabs-section");
const tabsList = document.getElementById("tabs-list");

// Load saved settings
chrome.storage.local.get(["serverUrl", "authToken", "authorizedDomains"], (data) => {
  serverUrlInput.value = data.serverUrl || "";
  authTokenInput.value = data.authToken || "";
  domainsTextarea.value = (data.authorizedDomains || []).join("\n");
  refreshStatus();
});

function refreshStatus() {
  chrome.runtime.sendMessage({ type: "get_status" }, (response) => {
    if (!response) return;

    const { connected, connecting, lastError } = response;
    let state = "disconnected";
    let label = "Disconnected";
    if (connected) { state = "connected"; label = "Connected"; }
    else if (connecting) { state = "connecting"; label = "Connecting…"; }

    statusBadge.className = `status-badge ${state}`;
    statusText.textContent = label;
    btnConnect.style.display = connected || connecting ? "none" : "block";
    btnDisconnect.style.display = connected ? "block" : "none";

    if (lastError && !connected && !connecting) {
      errorHint.textContent = lastError;
      errorHint.style.display = "block";
    } else {
      errorHint.style.display = "none";
    }

    if (connected && response.attachedTabs && response.attachedTabs.length > 0) {
      tabsSection.style.display = "block";
    }
  });
}

btnConnect.addEventListener("click", () => {
  const serverUrl = serverUrlInput.value.trim();
  const authToken = authTokenInput.value.trim();
  const domains = domainsTextarea.value
    .split("\n")
    .map((d) => d.trim())
    .filter(Boolean);

  if (!serverUrl) {
    serverUrlInput.style.borderColor = "#ef4444";
    return;
  }

  chrome.storage.local.set({ serverUrl, authToken, authorizedDomains: domains });

  chrome.runtime.sendMessage({
    type: "connect",
    serverUrl,
    authToken,
  });

  chrome.runtime.sendMessage({
    type: "update_domains",
    domains,
  });

  setTimeout(refreshStatus, 1000);
});

btnDisconnect.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "disconnect" });
  setTimeout(refreshStatus, 500);
});

// Auto-save domains on change
domainsTextarea.addEventListener("change", () => {
  const domains = domainsTextarea.value
    .split("\n")
    .map((d) => d.trim())
    .filter(Boolean);

  chrome.storage.local.set({ authorizedDomains: domains });
  chrome.runtime.sendMessage({ type: "update_domains", domains });
});

// Refresh status periodically while popup is open
setInterval(refreshStatus, 2000);
