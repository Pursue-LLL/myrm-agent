/** Recent-directory localStorage helpers for server browse popovers. */

export const MAX_RECENT_DIRS = 5;

export function getRecentDirectoryPaths(storageKey: string): string[] {
  if (typeof window === 'undefined') {return [];}
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) {return [];}
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {return [];}
    return parsed.filter((item): item is string => typeof item === 'string').slice(0, MAX_RECENT_DIRS);
  } catch {
    return [];
  }
}

export function rememberDirectoryPath(storageKey: string, dir: string): void {
  const current = getRecentDirectoryPaths(storageKey).filter((entry) => entry !== dir);
  localStorage.setItem(
    storageKey,
    JSON.stringify([dir, ...current].slice(0, MAX_RECENT_DIRS)),
  );
}

export function shortenHomePath(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+/, '~').replace(/^[A-Za-z]:\\Users\\[^\\]+/, '~');
}

export const DIRECTORY_GRANT_RECENT_KEY = 'myrm.directoryGrant.recent';
export const PROJECT_WORKSPACE_RECENT_KEY = 'myrm.projectWorkspace.recent';
