/** Session handoff from external source migration wizard to the main chat surface.
 *
 * [INPUT]
 * - localStorage / sessionStorage for one-shot migration anchors
 *
 * [OUTPUT]
 * - queue/consume helpers for agent, readiness anchor, bound project, workspace candidates
 *
 * [POS]
 * FE-only migration handoff SSOT between Settings/Onboarding and chat stream.
 */

export const MIGRATION_CHAT_AGENT_STORAGE_KEY = 'myrm:migration-chat-agent-id';
const MIGRATION_READINESS_ANCHOR_STORAGE_KEY = 'myrm:migration-readiness-anchor';
const MIGRATION_BOUND_PROJECT_STORAGE_KEY = 'myrm:migration-bound-project-id';
const MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY = 'myrm:migration-workspace-bind-candidates';
const LEGACY_MIGRATION_READINESS_ANCHOR_SESSION_KEY = 'myrm:migration-readiness-anchor';
const MIGRATION_READINESS_ANCHOR_TTL_MS = 30 * 60 * 1000;
const MIGRATION_HANDOFF_TTL_MS = 30 * 60 * 1000;

export type MigrationReadinessStatus = 'ready' | 'warning' | 'critical';

export interface MigrationWorkspaceBindCandidate {
  path: string;
  label: string;
  has_obsidian_config: boolean;
  markdown_file_count: number;
}

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

interface StoredMigrationHandoffEntry {
  value: string;
  queuedAt: string;
}

function readHandoffStorage(): Storage | null {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

function parseStoredHandoffEntry(raw: string): StoredMigrationHandoffEntry | null {
  try {
    const parsed = JSON.parse(raw) as { value?: unknown; queuedAt?: unknown };
    const value = typeof parsed.value === 'string' ? parsed.value.trim() : '';
    const queuedAt = typeof parsed.queuedAt === 'string' ? parsed.queuedAt.trim() : '';
    if (!value || !queuedAt) {
      return null;
    }
    const queuedAtMs = Date.parse(queuedAt);
    if (Number.isNaN(queuedAtMs) || Date.now() - queuedAtMs > MIGRATION_HANDOFF_TTL_MS) {
      return null;
    }
    return { value, queuedAt };
  } catch {
    return null;
  }
}

function writeHandoffEntry(storageKey: string, value: string): void {
  const storage = readHandoffStorage();
  if (storage === null || !value.trim()) {
    return;
  }
  storage.setItem(
    storageKey,
    JSON.stringify({
      value: value.trim(),
      queuedAt: new Date().toISOString(),
    } satisfies StoredMigrationHandoffEntry),
  );
}

export function queueMigrationBoundProjectId(projectId: string): void {
  writeHandoffEntry(MIGRATION_BOUND_PROJECT_STORAGE_KEY, projectId);
}

export function peekMigrationBoundProjectId(): string | null {
  const storage = readHandoffStorage();
  if (storage === null) {
    return null;
  }
  const raw = storage.getItem(MIGRATION_BOUND_PROJECT_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  const parsed = parseStoredHandoffEntry(raw);
  return parsed?.value ?? null;
}

export function consumeMigrationBoundProjectId(): string | null {
  const storage = readHandoffStorage();
  if (storage === null) {
    return null;
  }
  const raw = storage.getItem(MIGRATION_BOUND_PROJECT_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  const parsed = parseStoredHandoffEntry(raw);
  storage.removeItem(MIGRATION_BOUND_PROJECT_STORAGE_KEY);
  if (!parsed) {
    return null;
  }
  return parsed.value;
}

export function syncChatSidebarProjectId(chatId: string, projectId: string): void {
  const normalizedChatId = chatId.trim();
  const normalizedProjectId = projectId.trim();
  if (!normalizedChatId || !normalizedProjectId) {
    return;
  }

  void import('@/store/useChatStore').then(({ default: useChatStore }) => {
    const { chatHistoryItems, setChatHistoryItems } = useChatStore.getState();
    const existingIndex = chatHistoryItems.findIndex((item) => item.id === normalizedChatId);
    if (existingIndex === -1) {
      return;
    }
    const next = [...chatHistoryItems];
    next[existingIndex] = { ...next[existingIndex], projectId: normalizedProjectId };
    setChatHistoryItems(next);
  });
}

export function queueMigrationWorkspaceBindCandidates(candidates: MigrationWorkspaceBindCandidate[]): void {
  const storage = readHandoffStorage();
  if (storage === null) {
    return;
  }
  if (candidates.length === 0) {
    storage.removeItem(MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY);
    return;
  }
  storage.setItem(
    MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY,
    JSON.stringify({
      value: candidates,
      queuedAt: new Date().toISOString(),
    }),
  );
}

export function readMigrationWorkspaceBindCandidates(): MigrationWorkspaceBindCandidate[] {
  const storage = readHandoffStorage();
  if (storage === null) {
    return [];
  }
  const raw = storage.getItem(MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY);
  if (!raw) {
    return [];
  }
  try {
    const parsed = JSON.parse(raw) as { value?: unknown; queuedAt?: unknown };
    const queuedAt = typeof parsed.queuedAt === 'string' ? parsed.queuedAt.trim() : '';
    const queuedAtMs = Date.parse(queuedAt);
    if (!queuedAt || Number.isNaN(queuedAtMs) || Date.now() - queuedAtMs > MIGRATION_HANDOFF_TTL_MS) {
      storage.removeItem(MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY);
      return [];
    }
    const value = parsed.value;
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .map((item): MigrationWorkspaceBindCandidate | null => {
        if (!item || typeof item !== 'object') {
          return null;
        }
        const record = item as Record<string, unknown>;
        const path = typeof record.path === 'string' ? record.path.trim() : '';
        if (!path) {
          return null;
        }
        const label = typeof record.label === 'string' ? record.label.trim() : path;
        const mdCountRaw = record.markdown_file_count;
        const markdown_file_count =
          typeof mdCountRaw === 'number' ? mdCountRaw : Number(mdCountRaw ?? 0) || 0;
        return {
          path,
          label: label || path,
          has_obsidian_config: record.has_obsidian_config === true,
          markdown_file_count: Math.max(0, markdown_file_count),
        };
      })
      .filter((item): item is MigrationWorkspaceBindCandidate => item !== null);
  } catch {
    storage.removeItem(MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY);
    return [];
  }
}

export function clearMigrationWorkspaceBindCandidates(): void {
  const storage = readHandoffStorage();
  if (storage === null) {
    return;
  }
  storage.removeItem(MIGRATION_WORKSPACE_CANDIDATES_STORAGE_KEY);
}

/** Apply queued migration project bind to an existing chat (Settings bind while chat already in DB). */
export async function applyMigrationBoundProjectToChat(chatId: string): Promise<boolean> {
  const normalizedChatId = chatId.trim();
  const projectId = peekMigrationBoundProjectId();
  if (!normalizedChatId || !projectId) {
    return false;
  }

  try {
    const { moveChatToProject } = await import('@/services/projects');
    await moveChatToProject(normalizedChatId, projectId);
  } catch {
    return false;
  }

  consumeMigrationBoundProjectId();

  syncChatSidebarProjectId(normalizedChatId, projectId);

  return true;
}
