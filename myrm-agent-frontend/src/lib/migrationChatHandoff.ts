/** Session handoff from external source migration wizard to the main chat surface. */

export const MIGRATION_CHAT_AGENT_STORAGE_KEY = 'myrm:migration-chat-agent-id';
const MIGRATION_READINESS_ANCHOR_STORAGE_KEY = 'myrm:migration-readiness-anchor';

export type MigrationReadinessStatus = 'ready' | 'warning' | 'critical';

export interface MigrationReadinessAnchor {
  importBatchId: string;
  readinessStatus: MigrationReadinessStatus;
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

export function queueMigrationReadinessAnchor(anchor: MigrationReadinessAnchor): void {
  if (
    typeof window === 'undefined' ||
    !anchor.importBatchId.trim() ||
    !anchor.readinessStatus.trim()
  ) {
    return;
  }
  sessionStorage.setItem(
    MIGRATION_READINESS_ANCHOR_STORAGE_KEY,
    JSON.stringify({
      importBatchId: anchor.importBatchId.trim(),
      readinessStatus: anchor.readinessStatus,
    }),
  );
}

export function readMigrationReadinessAnchor(): MigrationReadinessAnchor | null {
  if (typeof window === 'undefined') {
    return null;
  }
  const raw = sessionStorage.getItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as {
      importBatchId?: unknown;
      readinessStatus?: unknown;
    };
    const importBatchId = typeof parsed.importBatchId === 'string' ? parsed.importBatchId.trim() : '';
    const readinessStatus = typeof parsed.readinessStatus === 'string' ? parsed.readinessStatus : '';
    if (
      !importBatchId ||
      (readinessStatus !== 'ready' && readinessStatus !== 'warning' && readinessStatus !== 'critical')
    ) {
      return null;
    }
    return {
      importBatchId,
      readinessStatus,
    };
  } catch {
    return null;
  }
}

export function clearMigrationReadinessAnchor(): void {
  if (typeof window === 'undefined') {
    return;
  }
  sessionStorage.removeItem(MIGRATION_READINESS_ANCHOR_STORAGE_KEY);
}

export function consumeMigrationReadinessAnchor(): MigrationReadinessAnchor | null {
  const anchor = readMigrationReadinessAnchor();
  if (anchor) {
    clearMigrationReadinessAnchor();
  }
  return anchor;
}
