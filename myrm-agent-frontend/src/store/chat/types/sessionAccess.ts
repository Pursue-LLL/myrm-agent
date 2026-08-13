/** Session-scoped HITL directory grant persisted on the chat row. */

export interface SessionAccessRoot {
  path: string;
  writable: boolean;
  label?: string;
  source?: string;
}

export function normalizeSessionAccessRoots(raw: unknown): SessionAccessRoot[] {
  if (!Array.isArray(raw)) {return [];}
  const roots: SessionAccessRoot[] = [];
  for (const item of raw) {
    if (!item || typeof item !== 'object') {continue;}
    const path = (item as { path?: unknown }).path;
    if (typeof path !== 'string' || !path.trim()) {continue;}
    const writable = (item as { writable?: unknown }).writable;
    const label = (item as { label?: unknown }).label;
    const source = (item as { source?: unknown }).source;
    roots.push({
      path: path.trim(),
      writable: typeof writable === 'boolean' ? writable : false,
      label: typeof label === 'string' && label.trim() ? label.trim() : undefined,
      source: typeof source === 'string' && source.trim() ? source.trim() : undefined,
    });
  }
  return roots;
}
