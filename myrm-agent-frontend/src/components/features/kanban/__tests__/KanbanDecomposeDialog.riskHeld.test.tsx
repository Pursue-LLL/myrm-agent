// @vitest-environment jsdom
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { installEnglishToastTranslator, jsonResponse, riskHeldRefusalBody, riskHeldTitle } from '@/test-utils/riskHeld';

const { sonnerToast, riskToast } = vi.hoisted(() => ({
  sonnerToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn() }),
  riskToast: Object.assign(vi.fn(), { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }),
}));

vi.mock('sonner', () => ({ toast: sonnerToast }));
vi.mock('@/lib/utils/toast', () => ({ toast: riskToast }));
vi.mock('@/lib/backend-health', () => ({
  ensureLocalBackendReady: vi.fn(async () => true),
  markLocalBackendUnreachable: vi.fn(),
}));
const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));

import type { DecomposeOutcome, KanbanTask } from '@/services/kanban';
import KanbanDecomposeDialog from '../KanbanDecomposeDialog';

const task = { task_id: 'task-1', title: 'Ship it', description: '' } as KanbanTask;

const fanoutPreview: DecomposeOutcome = {
  task_id: 'task-1',
  ok: true,
  fanout: true,
  children: [
    {
      title: 'Deploy with key sk-AAAAAABBBBBBCCCCCCDDDD-0',
      body: '',
      assignee: null,
      parent_indices: [],
      extra_skill_ids: [],
    },
  ],
  rationale: '',
  reason: '',
  new_title: null,
  new_body: null,
  new_assignee: null,
  child_ids: [],
  prompt_tokens: null,
  completion_tokens: null,
  persisted: false,
};

/** The preview is answered normally; the apply gets `applyReply`. */
function stubDecomposeApi(applyReply: () => Response): void {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: RequestInfo | URL) =>
      String(url).endsWith('/apply-decompose') ? applyReply() : jsonResponse(200, fanoutPreview),
    ),
  );
}

async function applyPreview(onOpenChange = vi.fn()): Promise<void> {
  render(<KanbanDecomposeDialog task={task} open onOpenChange={onOpenChange} />);
  fireEvent.click(await screen.findByText('decomposeApply'));
}

describe('applying a decomposition whose child titles the server holds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    installEnglishToastTranslator();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('explains the refusal once, adds no failure toast and keeps the dialog open for editing', async () => {
    stubDecomposeApi(() => jsonResponse(400, riskHeldRefusalBody));
    const onOpenChange = vi.fn();

    await applyPreview(onOpenChange);

    await waitFor(() => expect(riskToast.error).toHaveBeenCalledTimes(1));
    expect(riskToast.error.mock.calls[0]?.[0]).toBe(riskHeldTitle);
    expect(sonnerToast.error).not.toHaveBeenCalled();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it('still reports any other failure with its own toast', async () => {
    stubDecomposeApi(() => jsonResponse(500, { detail: 'boom' }));

    await applyPreview();

    await waitFor(() => expect(sonnerToast.error).toHaveBeenCalledWith('decomposeError'));
  });
});
