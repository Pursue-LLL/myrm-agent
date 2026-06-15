/** Session handoff from external source migration wizard to the main chat surface. */

export const MIGRATION_CHAT_AGENT_STORAGE_KEY = 'myrm:migration-chat-agent-id';

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
