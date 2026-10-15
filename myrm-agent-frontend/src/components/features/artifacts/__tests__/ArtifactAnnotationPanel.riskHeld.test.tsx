// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { panelToast, riskToast } = vi.hoisted(() => ({
  panelToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock('@/hooks/shared/useToast', () => ({ toast: panelToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
vi.mock('@/store/useChatStore', () => ({ default: { getState: () => ({ sendMessage: vi.fn() }) } }));
vi.mock('@/services/kanban', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/kanban')>()),
  listBoards: vi.fn(async () => ({ items: [{ board_id: 'board-1' }], total: 1 })),
  listTasks: vi.fn(async () => ({
    items: [{ task_id: 'task-1', status: 'in_review', attachments: [{ file_id: 'artifact-1' }] }],
    total: 1,
  })),
}));

import { ArtifactAnnotationPanel } from '../ArtifactAnnotationPanel';

const STORAGE_KEY = 'myrm.artifact-annotations.v1';

function seedOpenAnnotation(): void {
  localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      'artifact-1': [
        {
          id: 'a1',
          artifactId: 'artifact-1',
          versionId: 'v1',
          anchor: { startLine: 1, endLine: 1, textHash: 'abc', excerpt: 'the deploy script' },
          intent: 'use key sk-AAAAAABBBBBBCCCCCCDDDD-0 here',
          status: 'open',
          createdAt: '2030-01-01T00:00:00Z',
        },
      ],
    }),
  );
}

async function returnToTask(): Promise<void> {
  render(
    <ArtifactAnnotationPanel
      artifactId="artifact-1"
      artifactName="deploy.md"
      content="the deploy script"
      versionId="v1"
      chatId="chat-1"
      versionCount={1}
    />,
  );
  fireEvent.click(await screen.findByRole('button', { name: /annotation\.sendToTask/ }));
}

describe('returning artifact feedback to its task when the server holds the text', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
    seedOpenAnnotation();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem(STORAGE_KEY);
  });

  it('explains the held feedback once and keeps the annotations open for editing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(400, riskHeldRefusalBody)),
    );

    await returnToTask();

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(panelToast.error).not.toHaveBeenCalled();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? '{}')['artifact-1'][0].status).toBe('open');
  });

  it('still reports any other failure with its own toast', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponse(500, { detail: 'boom' })),
    );

    await returnToTask();

    await waitFor(() => expect(panelToast.error).toHaveBeenCalledTimes(1));
    expect(panelToast.error.mock.calls[0]?.[0]).toBe('annotation.sendFailed');
  });
});
