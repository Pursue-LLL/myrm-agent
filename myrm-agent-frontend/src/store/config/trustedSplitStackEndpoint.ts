/**
 * [INPUT]
 * (none: pure functions of a hostname or an API URL)
 *
 * [OUTPUT]
 * isTrustedSplitStackHostname: loopback, `.local`, RFC1918 and Tailscale CGNAT hosts are trusted; link-local (cloud
 * metadata) addresses, public IPs and external domains are not
 * isLocalOrTrustedSplitStackApiUrl: the same decision for an API URL, with or without a scheme
 *
 * [POS]
 * Tells whether an endpoint runs on the user's own machine or private network: a custom OpenAI-compatible provider
 * there needs no API key, and the model picker treats its models without a listed price as free.
 */

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname
    .toLowerCase()
    .trim()
    .replace(/^\[|\]$/g, '');
  if (normalized === 'localhost') {
    return true;
  }
  if (normalized === '127.0.0.1') {
    return true;
  }
  if (normalized === '::1') {
    return true;
  }
  if (normalized === '0.0.0.0') {
    return true;
  }
  return false;
}

export function isTrustedSplitStackHostname(hostname: string): boolean {
  const normalized = hostname
    .toLowerCase()
    .trim()
    .replace(/^\[|\]$/g, '');
  if (normalized === 'localhost' || normalized.endsWith('.local')) {
    return true;
  }
  if (isLoopbackHostname(normalized)) {
    return true;
  }

  const ipv4Parts = normalized.split('.');
  if (ipv4Parts.length === 4) {
    const p0 = Number(ipv4Parts[0]);
    const p1 = Number(ipv4Parts[1]);
    const p2 = Number(ipv4Parts[2]);
    const p3 = Number(ipv4Parts[3]);

    if ([p0, p1, p2, p3].every((p) => Number.isInteger(p) && p >= 0 && p <= 255)) {
      // Explicitly reject link-local (169.254.0.0/16, cloud metadata)
      if (p0 === 169 && p1 === 254) {
        return false;
      }
      // Loopback
      if (p0 === 127) {
        return true;
      }
      // RFC1918 10.0.0.0/8
      if (p0 === 10) {
        return true;
      }
      // RFC1918 172.16.0.0/12
      if (p0 === 172 && p1 >= 16 && p1 <= 31) {
        return true;
      }
      // RFC1918 192.168.0.0/16
      if (p0 === 192 && p1 === 168) {
        return true;
      }
      // Tailscale CGNAT 100.64.0.0/10
      if (p0 === 100 && p1 >= 64 && p1 <= 127) {
        return true;
      }
    }
  }

  return false;
}

export const isLocalOrTrustedSplitStackApiUrl = (apiUrl?: string | null): boolean => {
  if (!apiUrl) {
    return false;
  }
  const trimmed = apiUrl.trim();
  if (!trimmed) {
    return false;
  }
  const candidate = trimmed.includes('://') ? trimmed : `http://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    return isTrustedSplitStackHostname(parsed.hostname);
  } catch {
    return false;
  }
};
