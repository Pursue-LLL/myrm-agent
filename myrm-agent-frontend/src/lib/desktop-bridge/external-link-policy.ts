/**
 * [INPUT]
 * - win: Window-shaped host object, injected so the policy stays unit-testable
 * - openExternal: injected opener honoring the IShellBridge.openExternalUrl contract (POS: 外链通道；被拒绝时 resolve false，不 reject)
 *
 * [OUTPUT]
 * - installExternalLinkPolicy: patches win.open so new-window requests for http(s) URLs reach the system browser; returns the uninstall function
 *
 * [POS]
 * Desktop shell link routing policy. The shell (wry) drops window.open silently and its own interceptor only handles
 * <a target="_blank"> clicks, so this policy routes exactly the calls that cannot work there.
 */

type OpenExternal = (url: string) => Promise<boolean>;

/** An omitted or empty target opens a new window, exactly like _blank. */
function isNewWindowTarget(target: string | undefined): boolean {
  return !target || target.toLowerCase() === '_blank';
}

/** Resolves against the page like the browser would; only http(s) may leave the app. */
function resolveWebUrl(url: string | URL | undefined, base: string): string | null {
  if (url === undefined || url === '') {
    return null;
  }
  try {
    const resolved = new URL(url, base);
    return resolved.protocol === 'http:' || resolved.protocol === 'https:' ? resolved.href : null;
  } catch {
    return null;
  }
}

/**
 * Routes a new-window target (omitted, empty or _blank) with an http(s) URL to `openExternal`. Everything else
 * (_self/_parent/_top, named targets, other schemes, no URL) goes to the native implementation unchanged.
 */
export function installExternalLinkPolicy(win: Window, openExternal: OpenExternal): () => void {
  const nativeOpen = win.open;

  const policyOpen = function open(url?: string | URL, target?: string, features?: string): WindowProxy | null {
    const href = isNewWindowTarget(target) ? resolveWebUrl(url, win.location.href) : null;
    if (href === null) {
      return nativeOpen.call(win, url, target, features);
    }
    // The system browser hands back no window handle, so the result is null, as for any blocked popup.
    void openExternal(href);
    return null;
  };
  win.open = policyOpen;

  return () => {
    // Never clobber a wrapper that someone else installed on top of this one.
    if (win.open === policyOpen) {
      win.open = nativeOpen;
    }
  };
}
