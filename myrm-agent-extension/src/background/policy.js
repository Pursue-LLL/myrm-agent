/**
 * Access policy decisions: which URLs and tabs the Agent may use. Pure functions, no chrome APIs.
 *
 * [INPUT]
 * - access: { authorizedDomains: string[], allowAllEligibleTabs: boolean, pausedTabIds: Set<number>, agentTabIds: Set<number> }
 *   (the service-worker `state` satisfies this shape)
 *
 * [OUTPUT]
 * - isInternalBrowserUrl / isBlankUrl / isEligibleHttpUrl / extractDomain / matchDomain / isDomainAuthorized
 * - isTabEligibleForPolicy: the tab is on a domain the policy admits, or is a blank page the Agent opened (paused or not)
 * - isTabAuthorized: eligible and not paused
 * - isNavigationTargetAuthorized: the policy admits navigating to this URL
 *
 * [POS] The extension-side half of the domain boundary. The server enforces the same policy again; both must agree.
 */

export function isInternalBrowserUrl(url) {
  const trimmed = (url || "").trim();
  if (!trimmed) return true;
  const lowered = trimmed.toLowerCase();
  if (lowered === "about:blank" || lowered === "about:newtab") return false;
  return (
    lowered.startsWith("chrome://")
    || lowered.startsWith("chrome-extension://")
    || lowered.startsWith("devtools://")
    || lowered.startsWith("edge://")
    || lowered.startsWith("brave://")
  );
}

export function isBlankUrl(url) {
  const trimmed = (url || "").trim().toLowerCase();
  return trimmed === "" || trimmed === "about:blank";
}

export function isEligibleHttpUrl(url) {
  const trimmed = (url || "").trim();
  if (!trimmed || isInternalBrowserUrl(trimmed)) return false;
  try {
    const parsed = new URL(trimmed);
    const scheme = (parsed.protocol || "").replace(":", "").toLowerCase();
    if (!["http", "https", "file"].includes(scheme)) return false;
    return Boolean(parsed.hostname) || scheme === "file";
  } catch {
    return false;
  }
}

export function extractDomain(url) {
  try {
    return new URL(url).hostname;
  } catch {
    return "";
  }
}

export function matchDomain(domain, pattern) {
  if (pattern.startsWith("*.")) {
    const suffix = pattern.slice(2);
    return domain === suffix || domain.endsWith("." + suffix);
  }
  return domain === pattern;
}

export function isDomainAuthorized(domain, access) {
  return access.authorizedDomains.some((pattern) => matchDomain(domain, pattern));
}

export function isTabEligibleForPolicy(tab, access) {
  if (!tab || !Number.isInteger(tab.id)) return false;
  // A blank page the Agent opened holds no site data; it is admitted so the Agent can take it to the site it needs.
  if (access.agentTabIds.has(tab.id) && isBlankUrl(tab.url)) return true;
  const url = tab.url || "";
  if (isInternalBrowserUrl(url)) return false;
  if (access.allowAllEligibleTabs) {
    return isEligibleHttpUrl(url);
  }
  if (!access.authorizedDomains.length) return false;
  const domain = extractDomain(url);
  return isDomainAuthorized(domain, access);
}

export function isTabAuthorized(tab, access) {
  if (!tab || !Number.isInteger(tab.id)) return false;
  if (access.pausedTabIds.has(tab.id)) return false;
  return isTabEligibleForPolicy(tab, access);
}

export function isNavigationTargetAuthorized(url, access) {
  if (isInternalBrowserUrl(url)) return false;
  if (access.allowAllEligibleTabs) {
    return isEligibleHttpUrl(url);
  }
  if (!access.authorizedDomains.length) return false;
  const domain = extractDomain(url).toLowerCase();
  return domain ? isDomainAuthorized(domain, access) : false;
}
