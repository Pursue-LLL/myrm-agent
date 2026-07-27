/** Session handoff from external source migration wizard to the main chat surface. */

export const MIGRATION_CHAT_AGENT_STORAGE_KEY = 'myrm:migration-chat-agent-id';
const MIGRATION_READINESS_ANCHOR_STORAGE_KEY = 'myrm:migration-readiness-anchor';
const LEGACY_MIGRATION_READINESS_ANCHOR_SESSION_KEY = 'myrm:migration-readiness-anchor';
const MIGRATION_READINESS_ANCHOR_TTL_MS = 30 * 60 * 1000;

export type MigrationReadinessStatus = 'ready' | 'warning' | 'critical';

export interface MigrationReadinessAnchor {
  importBatchId: string;
  readinessStatus: MigrationReadinessStatus;
  targetAgentId: string;
  queuedAt: string;
}

interface StoredMigrationReadinessAnchor {
  importBatchId: string;
  readinessStatus: MigrationReadinessStatus;
  targetAgentId: string;
  queuedAt: string;
}

function readAnchorStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

function migrateLegacySessionAnchorToLocalStorage(): void {
  if (typeof window === 'undefined') {
    return;
  }
  const legacyRaw = window.sessionStorage.getItem(LEGACY_MIGRATION_READINESS_ANCHOR_SESSION_KEY);
  if (!legacyRaw) {
    return;
  }
  if (!window.localStorage.getItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY)) {
    window.localStorage.setItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY, legacyRaw);
  }
  window.sessionStorage.removeItem(LEGACY_MIGRATION_READINESS_ANCHOR_SESSION_KEY);
}

export function queueMigrationChatAgent(agentId: string): void {
  if (typeof window === 'undefined' || !agentId.trim()) {
    return;
  }
  sessionStorage.setItem(MIGRATION_CHAT_AGENT_STORAGE_KEY, agentId.trim());
}

export function consumeMigrationChatAgent(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const agentId = sessionStorage.getItem(MIGRATION_CHAT_AGENT_STORAGE_KEY);
  if (!agentId) {
    return null;
  }
  sessionStorage.removeItem(MIGRATION_CHAT_AGENT_STORAGE_KEY);
  return agentId;
}

export function queueMigrationReadinessAnchor(anchor: {
  importBatchId: string;
  readinessStatus: MigrationReadinessStatus;
  targetAgentId: string;
}): void {
  const storage = readAnchorStorage();
  if (
    storage === null ||
    !anchor.importBatchId.trim() ||
    !anchor.readinessStatus.trim() ||
    !anchor.targetAgentId.trim()
  ) {
    return;
  }
  storage.setItem(
    MIGRATION_READINESS_ANCHOR_STORAGE_KEY,
    JSON.stringify({
      importBatchId: anchor.importBatchId.trim(),
      readinessStatus: anchor.readinessStatus,
      targetAgentId: anchor.targetAgentId.trim(),
      queuedAt: new Date().toISOString(),
    } satisfies StoredMigrationReadinessAnchor),
  );
}

function parseStoredMigrationReadinessAnchor(raw: string): StoredMigrationReadinessAnchor | null {
  try {
    const parsed = JSON.parse(raw) as {
      importBatchId?: unknown;
      readinessStatus?: unknown;
      targetAgentId?: unknown;
      queuedAt?: unknown;
    };
    const importBatchId = typeof parsed.importBatchId === 'string' ? parsed.importBatchId.trim() : '';
    const readinessStatus = typeof parsed.readinessStatus === 'string' ? parsed.readinessStatus : '';
    const targetAgentId = typeof parsed.targetAgentId === 'string' ? parsed.targetAgentId.trim() : '';
    const queuedAt = typeof parsed.queuedAt === 'string' ? parsed.queuedAt.trim() : '';
    if (
      !importBatchId ||
      !targetAgentId ||
      !queuedAt ||
      (readinessStatus !== 'ready' && readinessStatus !== 'warning' && readinessStatus !== 'critical')
    ) {
      return null;
    }
    const queuedAtMs = Date.parse(queuedAt);
    if (Number.isNaN(queuedAtMs) || Date.now() - queuedAtMs > MIGRATION_READINESS_ANCHOR_TTL_MS) {
      return null;
    }
    return {
      importBatchId,
      readinessStatus,
      targetAgentId,
      queuedAt,
    };
  } catch {
    return null;
  }
}

export function readMigrationReadinessAnchor(): MigrationReadinessAnchor | null {
  const storage = readAnchorStorage();
  if (storage === null) {
    return null;
  }
  migrateLegacySessionAnchorToLocalStorage();
  const raw = storage.getItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  const parsed = parseStoredMigrationReadinessAnchor(raw);
  if (!parsed) {
    storage.removeItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY);
    return null;
  }
  return parsed;
}

export function clearMigrationReadinessAnchor(): void {
  const storage = readAnchorStorage();
  if (storage === null) {
    return;
  }
  storage.removeItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY);
  if (typeof window !== 'undefined') {
    window.sessionStorage.removeItem(LEGACY_MIGRATION_READINESS_ANCHOR_SESSION_KEY);
  }
}

export function consumeMigrationReadinessAnchorForAgent(agentId: string): MigrationReadinessAnchor | null {
  const normalizedAgentId = agentId.trim();
  if (!normalizedAgentId) {
    return null;
  }
  const anchor = readMigrationReadinessAnchor();
  if (!anchor || anchor.targetAgentId !== normalizedAgentId) {
    return null;
  }
  clearMigrationReadinessAnchor();
  return anchor;
}

export function consumeMigrationReadinessAnchor(): MigrationReadinessAnchor | null {
  const anchor = readMigrationReadinessAnchor();
  if (anchor) {
    clearMigrationReadinessAnchor();
  }
  return anchor;
}
