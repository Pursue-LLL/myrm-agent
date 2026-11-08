/**
 * [INPUT]
 * @/store/useProjectStore::useProjectStore (POS: Project list and sidebar project filter store)
 *
 * [OUTPUT]
 * resolveKanbanProjectScope: The project a kanban board lookup is scoped to (migration-bound project first, then the sidebar filter).
 *
 * [POS]
 * Shared by the request builder (default board id) and the send guard (board required) so both read the same scope.
 */

import { useProjectStore } from '@/store/useProjectStore';

export function resolveKanbanProjectScope(migrationBoundProjectId: string | null | undefined): string | null {
  const migrationScope = migrationBoundProjectId?.trim();
  if (migrationScope) {
    return migrationScope;
  }
  const activeFilter = useProjectStore.getState().activeFilter;
  if (typeof activeFilter !== 'string') {
    return null;
  }
  const trimmed = activeFilter.trim();
  return trimmed || null;
}
