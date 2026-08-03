/** Extract basename and truncate for humanize display. */

export function trunc(value: string, maxLen: number): string {
  if (value.length <= maxLen) {
    return value;
  }
  return `${value.slice(0, maxLen - 1)}…`;
}

export function baseName(path: string): string {
  const trimmed = path.replace(/\/+$/, '');
  const parts = trimmed.split(/[/\\]/);
  return parts[parts.length - 1] || trimmed || path;
}

export function displayUrlHost(url: string): string {
  try {
    const host = new URL(url).host;
    return host ? trunc(host, 50) : trunc(url, 50);
  } catch {
    return trunc(url, 50);
  }
}
