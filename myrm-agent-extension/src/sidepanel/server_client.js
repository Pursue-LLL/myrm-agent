/**
 * Side Panel connection to myrm-agent-server: where it is, how to authenticate, and whether it answers.
 *
 * [INPUT]
 * - `chrome.storage.local` settings `serverUrl` (the WebSocket URL of the extension bridge) and `authToken`
 *
 * [OUTPUT]
 * - createServerClient: `start()` follows the settings and reports `disconnected | connecting | connected | error`
 *   through `onStatus`; `apiFetch(path, options)` is `fetch` against the server with the bearer token
 *
 * [POS] Transport settings of the Side Panel; the HTTP+SSE chat protocol lives in sidepanel.js.
 */

/**
 * @param {string} bridgeUrl the stored WebSocket URL of the extension bridge
 * @returns {string} the HTTP base URL of the same server, or "" when none is configured
 */
function httpBaseUrl(bridgeUrl) {
  return bridgeUrl
    .replace(/^ws:/, "http:")
    .replace(/^wss:/, "https:")
    .replace(/\/api\/v1\/ws\/extension\/?$/, "")
    .replace(/\/ws\/extension\/?$/, "")
    .replace(/\/$/, "");
}

/**
 * @param {(status: "disconnected" | "connecting" | "connected" | "error") => void} onStatus
 */
export function createServerClient(onStatus) {
  let baseUrl = "";
  let authToken = "";

  /**
   * @param {string} path
   * @param {RequestInit} [options]
   * @returns {Promise<Response>}
   */
  function apiFetch(path, options = {}) {
    const headers = {
      "Content-Type": "application/json",
      ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
      ...options.headers,
    };
    return fetch(`${baseUrl}${path}`, { ...options, headers });
  }

  async function checkConnection() {
    if (!baseUrl) {
      onStatus("disconnected");
      return;
    }
    onStatus("connecting");
    try {
      const resp = await apiFetch("/api/v1/health", { method: "GET" });
      onStatus(resp.ok ? "connected" : "error");
    } catch {
      onStatus("error");
    }
  }

  function loadConfig() {
    chrome.storage.local.get(["serverUrl", "authToken"], (data) => {
      authToken = data.authToken || "";
      baseUrl = httpBaseUrl(data.serverUrl || "");
      checkConnection();
    });
  }

  return {
    apiFetch,
    start() {
      loadConfig();
      chrome.storage.onChanged.addListener((changes) => {
        if (changes.serverUrl || changes.authToken) loadConfig();
      });
    },
  };
}
