/**
 * Wiki Settings deep-link builders for extension popup.
 */

export function wikiHttpBaseFromServerUrl(url) {
  if (!url) return "";
  return url
    .replace(/^ws:/i, "http:")
    .replace(/^wss:/i, "https:")
    .replace(/\/api\/v1\/ws\/extension\/?$/i, "");
}

function settingsWikiBase(webUiOrigin, clipAgentId) {
  if (!webUiOrigin) return "";
  const params = new URLSearchParams();
  if (clipAgentId) params.set("agentId", clipAgentId);
  const query = params.toString();
  return `${webUiOrigin.replace(/\/$/, "")}/settings/wiki${query ? `?${query}` : ""}`;
}

export function buildDuplicateReviewUrl(webUiOrigin, clipAgentId) {
  const base = settingsWikiBase(webUiOrigin, clipAgentId);
  if (!base) return "";
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}wikiTab=duplicateReview`;
}

export function buildWikiIgnoreUrl(webUiOrigin, clipAgentId) {
  const base = settingsWikiBase(webUiOrigin, clipAgentId);
  if (!base) return "";
  const sep = base.includes("?") ? "&" : "?";
  return `${base}${sep}wikiTab=overview&focus=wikiignore`;
}

export function buildClipRawUrl(webUiOrigin, clipAgentId, relativePath) {
  if (!webUiOrigin || !relativePath) return "";
  const params = new URLSearchParams();
  if (clipAgentId) params.set("agentId", clipAgentId);
  params.set("wikiTab", "overview");
  params.set("rawPath", relativePath.replace(/^\//, ""));
  return `${webUiOrigin.replace(/\/$/, "")}/settings/wiki?${params.toString()}`;
}

export function buildWikiClipPostUrl(serverUrl, clipAgentId) {
  const httpBase = wikiHttpBaseFromServerUrl(serverUrl).replace(/\/$/, "");
  let url = `${httpBase}/api/v1/wiki/clip`;
  if (clipAgentId) {
    url += `?agent_id=${encodeURIComponent(clipAgentId)}`;
  }
  return url;
}
