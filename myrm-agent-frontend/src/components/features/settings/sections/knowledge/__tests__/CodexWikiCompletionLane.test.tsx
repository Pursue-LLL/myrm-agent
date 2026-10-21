/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CodexWikiCompletionLane from '../CodexWikiCompletionLane';

const pushMock = vi.fn();
const queueVaultMock = vi.fn();

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: pushMock }),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock('@/services/onboarding', () => ({
  applySecondBrainPreset: vi.fn().mockResolvedValue({ message: 'ok' }),
}));

vi.mock('@/lib/migrationChatHandoff', () => ({
  queueMigrationObsidianVaultImport: (...args: unknown[]) => queueVaultMock(...args),
}));

describe('CodexWikiCompletionLane', () => {
  it('renders completion lane and queues vault handoff before wiki import navigation', () => {
    render(
      <CodexWikiCompletionLane
        targetAgentId="agent-1"
        vaultCandidate={{
          path: '/tmp/vault',
          label: 'Codex Obsidian vault',
          has_obsidian_config: true,
          markdown_file_count: 3,
        }}
      />,
    );
    expect(screen.getByTestId('codex-wiki-completion-lane')).toBeTruthy();
    expect(screen.getByTestId('codex-completion-vault-hint')).toBeTruthy();
    fireEvent.click(screen.getByTestId('codex-completion-import-wiki'));
    expect(queueVaultMock).toHaveBeenCalledWith({
      vaultPath: '/tmp/vault',
      targetAgentId: 'agent-1',
    });
    expect(pushMock).toHaveBeenCalledWith('/settings/wiki?agentId=agent-1#wiki-obsidian-import');
  });
});
