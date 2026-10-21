/** Browser-local WebUI access prefs (Tauri uses native system config). */

const STORAGE_KEY = 'myrm-webui-access-prefs';

export type WebuiAccessPrefs = {
  enableRemoteAccess: boolean;
};

export function loadWebuiAccessPrefs(): WebuiAccessPrefs | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as Partial<WebuiAccessPrefs>;
    if (typeof parsed.enableRemoteAccess !== 'boolean') {
      return null;
    }
    return { enableRemoteAccess: parsed.enableRemoteAccess };
  } catch {
    return null;
  }
}

export function saveWebuiAccessPrefs(prefs: WebuiAccessPrefs): void {
  if (typeof window === 'undefined') {
    return;
  }
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}
