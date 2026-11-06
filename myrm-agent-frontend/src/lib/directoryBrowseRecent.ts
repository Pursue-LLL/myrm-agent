/** Recent-directory localStorage helpers for server browse popovers. */

export const MAX_RECENT_DIRS = 5;

export function getRecentDirectoryPaths(storageKey: string): string[] {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = localStorage.getItem(storageKey);
    if (!raw) {
      return [];
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.filter((item): item is string => typeof item === 'string').slice(0, MAX_RECENT_DIRS);
  } catch {
    return [];
  }
}

/** The list is a convenience: storage that refuses the write (quota, private mode) must not fail the pick itself. */
export function rememberDirectoryPath(storageKey: string, dir: string): void {
  const current = getRecentDirectoryPaths(storageKey).filter((entry) => entry !== dir);
  try {
    localStorage.setItem(storageKey, JSON.stringify([dir, ...current].slice(0, MAX_RECENT_DIRS)));
  } catch {
    // Dropped on purpose; the next pick tries again.
  }
}

export function shortenHomePath(path: string): string {
  return path.replace(/^\/(?:Users|home)\/[^/]+/, '~').replace(/^[A-Za-z]:\\Users\\[^\\]+/, '~');
}

export const DIRECTORY_GRANT_RECENT_KEY = 'myrm.directoryGrant.recent';
export const PROJECT_WORKSPACE_RECENT_KEY = 'myrm.projectWorkspace.recent';
export const WORKSPACE_PICKER_RECENT_KEY = 'myrm.workspaceDirPicker.recent';
