/**
 * [INPUT]
 * - DOM Window contract only (any Window-shaped object, which keeps the policy unit-testable)
 *
 * [OUTPUT]
 * - installExternalLinkPolicy: routes window.open new-window requests for http(s) URLs to the system browser, returns an uninstall function
 *
 * [POS]
 * The desktop shell (wry) opens no window for window.open and drops the request silently; the shell's own
 * interceptor only handles <a target="_blank"> clicks. This policy rewrites exactly the calls that cannot work
 * there: a new-window target (omitted, empty or _blank) with an http(s) URL. Everything else (_self/_parent/_top,
 * named targets, other schemes, no URL) goes to the native implementation unchanged.
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
