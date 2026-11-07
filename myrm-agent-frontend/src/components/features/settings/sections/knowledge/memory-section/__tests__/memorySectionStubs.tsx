import type { ReactNode } from 'react';

import type { MemoryTab } from '@/components/features/memory/settings/MemoryTabSwitcher';
import type { Memory, MemoryPaginationInfo, MemoryType } from '@/services/memory';
import type { MemoryImportDryRunResult } from '@/services/memory/archive';

/**
 * 记忆面板子组件的替身：只回显收到的 props，并把回调暴露成按钮，
 * 让测试断言“面板把什么传给了子组件、子组件触发回调后面板做了什么”。
 */

const TABS: MemoryTab[] = ['pending', 'all', 'context', 'shared', 'recall', 'trash'];

interface OpenProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const marker = (testId: string) =>
  function Marker() {
    return <div data-testid={testId} />;
  };

export const openFlagDialog = (testId: string) =>
  function OpenFlagDialog({ open, onOpenChange }: OpenProps) {
    return (
      <div data-testid={testId} data-open={String(open)}>
        <button type="button" onClick={() => onOpenChange(false)}>
          {`${testId}:close`}
        </button>
      </div>
    );
  };

export const memoryDialog = (testId: string) =>
  function MemoryDialog({ memory, open, onOpenChange }: OpenProps & { memory: Memory | null }) {
    return (
      <div data-testid={testId} data-open={String(open)} data-memory={memory?.id ?? ''}>
        <button type="button" onClick={() => onOpenChange(false)}>
          {`${testId}:close`}
        </button>
      </div>
    );
  };

export function ClearAllDialog({
  open,
  isClearing,
  onOpenChange,
  onConfirm,
}: OpenProps & { isClearing: boolean; onConfirm: () => void }) {
  return (
    <div data-testid="clear-dialog" data-open={String(open)} data-clearing={String(isClearing)}>
      <button type="button" onClick={onConfirm}>
        clear:confirm
      </button>
      <button type="button" onClick={() => onOpenChange(false)}>
        clear:close
      </button>
    </div>
  );
}

export function ImportReviewDialog({
  open,
  dryRun,
  expiresAt,
  importing,
  onOpenChange,
  onConfirm,
}: OpenProps & {
  dryRun: MemoryImportDryRunResult | null;
  expiresAt: string | null;
  importing: boolean;
  onConfirm: () => void;
}) {
  return (
    <div
      data-testid="import-review"
      data-open={String(open)}
      data-importing={String(importing)}
      data-expires={expiresAt ?? ''}
      data-source={dryRun?.summary.source ?? ''}
    >
      <button type="button" onClick={onConfirm}>
        review:confirm
      </button>
      <button type="button" onClick={() => onOpenChange(false)}>
        review:close
      </button>
    </div>
  );
}

export function TabSwitcher({
  activeTab,
  pendingCount,
  totalCount,
  archivedCount,
  onChange,
}: {
  activeTab: MemoryTab;
  pendingCount: number;
  totalCount?: number;
  archivedCount?: number;
  onChange: (tab: MemoryTab) => void;
}) {
  return (
    <div
      data-testid="tab-switcher"
      data-active={activeTab}
      data-pending={pendingCount}
      data-total={totalCount ?? ''}
      data-archived={archivedCount ?? ''}
    >
      {TABS.map((tab) => (
        <button key={tab} type="button" onClick={() => onChange(tab)}>
          {`tab:${tab}`}
        </button>
      ))}
    </div>
  );
}

export function MemoryCardStub({
  memory,
  variant,
  onClick,
  onEdit,
  onDelete,
  onToggleDisable,
  onChatFromMemory,
  onToggleProtect,
}: {
  memory: Memory;
  variant: string;
  onClick: () => void;
  onEdit: () => void;
  onDelete: (permanent: boolean) => void;
  onToggleDisable: () => void;
  onChatFromMemory: () => void;
  onToggleProtect: (nextLocked: boolean) => void;
}) {
  const { id } = memory;
  const action = (label: string, run: () => void) => (
    <button type="button" onClick={run}>
      {`${label} ${id}`}
    </button>
  );
  return (
    <div data-testid={`card-${id}`} data-variant={variant}>
      {action('open', onClick)}
      {action('edit', onEdit)}
      {action('delete', () => onDelete(false))}
      {action('purge', () => onDelete(true))}
      {action('toggle', onToggleDisable)}
      {action('chat', onChatFromMemory)}
      {action('protect', () => onToggleProtect(true))}
      {action('unprotect', () => onToggleProtect(false))}
    </div>
  );
}

export function TrashPanel({
  memories,
  loading,
  pagination,
  onRestore,
  onPurge,
  onLoadMore,
}: {
  memories: Memory[];
  loading: boolean;
  pagination: MemoryPaginationInfo | null;
  onRestore: (id: string) => Promise<void>;
  onPurge: (id: string) => Promise<void>;
  onLoadMore: () => void;
}) {
  return (
    <div
      data-testid="trash-panel"
      data-count={memories.length}
      data-loading={String(loading)}
      data-next={String(pagination?.has_next ?? false)}
    >
      <button type="button" onClick={() => void onRestore('trashed-1')}>
        trash:restore
      </button>
      <button type="button" onClick={() => void onPurge('trashed-1')}>
        trash:purge
      </button>
      <button type="button" onClick={onLoadMore}>
        trash:more
      </button>
    </div>
  );
}

export function SettingsToggles({ enableMemory }: { enableMemory: boolean }) {
  return <div data-testid="settings-toggles" data-enabled={String(enableMemory)} />;
}

export function LoginPromptStub({ title, description }: { title: string; description: string }) {
  return <div data-testid="login-prompt">{`${title}|${description}`}</div>;
}

export function PendingList({ showBatchActions }: { showBatchActions?: boolean }) {
  return <div data-testid="pending-list" data-batch={String(showBatchActions ?? false)} />;
}

export function TypeIcon({ type }: { type: MemoryType }) {
  return <i data-testid={`type-icon-${type}`} />;
}

export const Passthrough = ({ children }: { children?: ReactNode }) => <>{children}</>;

export const TooltipBody = ({ children }: { children?: ReactNode }) => <div data-tooltip="">{children}</div>;
