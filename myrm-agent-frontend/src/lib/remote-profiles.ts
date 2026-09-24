/**
 * [INPUT]
 * - window.localStorage (`myrm-remote-gateway-roster` / legacy `myrm-remote-gateway`)
 *
 * [OUTPUT]
 * - RemoteConnectionProfile roster CRUD + active selection SSOT.
 * - Legacy single-slot migration (once, then delete legacy key).
 *
 * [POS]
 * Tauri Remote Profile 连接档案 SSOT。server-authoritative，桌面不镜像远端状态。
 */

export type RemoteProfileKind = 'server' | 'cloud';

export interface RemoteConnectionProfile {
  id: string;
  name: string;
  url: string;
  kind: RemoteProfileKind;
  cpBaseUrl?: string;
}

/** Cloud 档案经 CP 代理访问用户沙箱（SaaS 约定 `https://<cp-host>/proxy/me`）。 */
export function resolveProfileApiBase(profile: RemoteConnectionProfile): string {
  if (profile.kind === 'cloud' && profile.cpBaseUrl) {
    return `${profile.cpBaseUrl.replace(/\/+$/, '')}/proxy/me`;
  }
  return profile.url;
}

interface RosterPayload {
  profiles: RemoteConnectionProfile[];
  activeId: string | null;
}

const ROSTER_STORAGE_KEY = 'myrm-remote-gateway-roster';
const LEGACY_STORAGE_KEY = 'myrm-remote-gateway';
const MAX_NAME_LENGTH = 64;

function isBrowser(): boolean {
  return typeof window !== 'undefined' && !!window.localStorage;
}

function normalizeUrl(raw: string): string | null {
  const url = raw.trim().replace(/\/+$/, '');
  if (!url) {
    return null;
  }
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return null;
    }
  } catch {
    return null;
  }
  return url;
}

function normalizeName(raw: string): string | null {
  const name = raw.trim();
  if (!name || name.length > MAX_NAME_LENGTH) {
    return null;
  }
  return name;
}

function readRoster(): RosterPayload {
  if (!isBrowser()) {
    return { profiles: [], activeId: null };
  }
  try {
    const raw = window.localStorage.getItem(ROSTER_STORAGE_KEY);
    if (!raw) {
      return migrateLegacyOnce();
    }
    const parsed = JSON.parse(raw) as Partial<RosterPayload>;
    const profiles = Array.isArray(parsed.profiles)
      ? parsed.profiles
          .filter(
            (p): p is RemoteConnectionProfile =>
              !!p && typeof p.id === 'string' && typeof p.name === 'string' && typeof p.url === 'string',
          )
          .map((p) => ({
            ...p,
            kind: p.kind === 'cloud' ? ('cloud' as const) : ('server' as const),
          }))
      : [];
    const activeId =
      typeof parsed.activeId === 'string' && profiles.some((p) => p.id === parsed.activeId)
        ? parsed.activeId
        : null;
    return { profiles, activeId };
  } catch {
    return { profiles: [], activeId: null };
  }
}

function migrateLegacyOnce(): RosterPayload {
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (!raw) {
      return { profiles: [], activeId: null };
    }
    const parsed = JSON.parse(raw) as { enabled?: boolean; url?: string };
    const url = typeof parsed.url === 'string' ? normalizeUrl(parsed.url) : null;
    if (!parsed.enabled || !url) {
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
      return { profiles: [], activeId: null };
    }
    const profile: RemoteConnectionProfile = {
      id: `remote-${Date.now()}`,
      name: 'Remote server',
      url,
      kind: 'server',
    };
    const roster: RosterPayload = { profiles: [profile], activeId: profile.id };
    window.localStorage.setItem(ROSTER_STORAGE_KEY, JSON.stringify(roster));
    window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    return roster;
  } catch {
    try {
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      // ignore
    }
    return { profiles: [], activeId: null };
  }
}

function writeRoster(roster: RosterPayload): void {
  if (!isBrowser()) {
    return;
  }
  window.localStorage.setItem(ROSTER_STORAGE_KEY, JSON.stringify(roster));
}

export function listRemoteProfiles(): RemoteConnectionProfile[] {
  return readRoster().profiles;
}

export function getActiveRemoteProfile(): RemoteConnectionProfile | null {
  const roster = readRoster();
  if (!roster.activeId) {
    return null;
  }
  return roster.profiles.find((p) => p.id === roster.activeId) ?? null;
}

export function getActiveRemoteProfileId(): string | null {
  return readRoster().activeId;
}

export interface AddRemoteProfileOptions {
  kind?: RemoteProfileKind;
  cpBaseUrl?: string;
}

export function addRemoteProfile(
  name: string,
  url: string,
  opts?: AddRemoteProfileOptions,
): RemoteConnectionProfile | null {
  const cleanName = normalizeName(name);
  const cleanUrl = normalizeUrl(url);
  if (!cleanName || !cleanUrl) {
    return null;
  }
  const kind: RemoteProfileKind = opts?.kind === 'cloud' ? 'cloud' : 'server';
  const cpBaseUrl = kind === 'cloud' && opts?.cpBaseUrl ? normalizeUrl(opts.cpBaseUrl) : undefined;
  if (kind === 'cloud' && !cpBaseUrl) {
    return null;
  }
  const roster = readRoster();
  if (roster.profiles.some((p) => p.name.toLowerCase() === cleanName.toLowerCase())) {
    return null;
  }
  if (roster.profiles.some((p) => p.url === cleanUrl)) {
    return null;
  }
  const profile: RemoteConnectionProfile = {
    id: `remote-${Date.now()}-${Math.floor(Math.random() * 10000)}`,
    name: cleanName,
    url: cleanUrl,
    kind,
    ...(cpBaseUrl ? { cpBaseUrl } : {}),
  };
  roster.profiles.push(profile);
  roster.activeId = profile.id;
  writeRoster(roster);
  return profile;
}

export function removeRemoteProfile(id: string): void {
  const roster = readRoster();
  roster.profiles = roster.profiles.filter((p) => p.id !== id);
  if (roster.activeId === id) {
    roster.activeId = null;
  }
  writeRoster(roster);
}

export function setActiveRemoteProfileId(id: string | null): boolean {
  const roster = readRoster();
  if (id !== null && !roster.profiles.some((p) => p.id === id)) {
    return false;
  }
  roster.activeId = id;
  writeRoster(roster);
  return true;
}

export function isValidRemoteProfileInput(name: string, url: string): boolean {
  return normalizeName(name) !== null && normalizeUrl(url) !== null;
}
