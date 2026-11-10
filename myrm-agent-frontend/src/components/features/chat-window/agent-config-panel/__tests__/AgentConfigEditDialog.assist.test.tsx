/**
 * What the edit dialog asks the server for on the instruction card.
 *
 * Real scenario: the user lets the model write a prompt (streamed into the draft) and reads the version history of a
 * saved agent. A slow or failing server must never leave the user without a word, and a dialog showing any other
 * card asks for no history. The estimate of the other cards is in AgentConfigEditDialog.estimate.test.tsx.
 */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { deferred } from '@/test-utils/deferred';

import type { ConfigCardType } from '../AgentConfigCards';
import { dialogProps, instructionPanel, kit, resetKit, type DialogProps } from './editDialogKit';
import { bodyOf, fetchMock, installFakeServer, json, requests, sse, stream, watched } from './editDialogRequests';

vi.mock('next/dynamic', async () => (await import('./editDialogKit')).nextDynamicMock());
vi.mock('@/hooks/billing/useFeatureEntitlements', async () => (await import('./editDialogKit')).entitlementsMock());
vi.mock('@/lib/deploy-mode', async (importOriginal) =>
  (await import('./editDialogKit')).deployModeMock(await importOriginal<typeof import('@/lib/deploy-mode')>()),
);
vi.mock('@/hooks/shared/useToast', async () => ({ toast: (await import('./editDialogKit')).kit.toast }));
vi.mock('@/services/riskHeldToast', async (importOriginal) => {
  const { kit: shared } = await import('./editDialogKit');
  return {
    ...(await importOriginal<typeof import('@/services/riskHeldToast')>()),
    riskHeldErrorFromResponse: (response: Response) => shared.riskHeld(response),
  };
});
vi.mock('../ActionSpaceAccuracyRadar', async () => (await import('./editDialogKit')).radarMock());
vi.mock('../SkillsSectionPanel', async () => (await import('./editDialogKit')).skillsPanelMock());
vi.mock('../BuiltinToolsPanel', async () => (await import('./editDialogKit')).builtinToolsPanelMock());
vi.mock('../SubagentsPanel', async () => (await import('./editDialogKit')).subagentsPanelMock());
vi.mock('../InstructionPanel', async () => (await import('./editDialogKit')).instructionPanelMock());

import AgentConfigEditDialog from '../AgentConfigEditDialog';

function show(type: ConfigCardType, overrides: Partial<DialogProps> = {}) {
  return render(<AgentConfigEditDialog {...dialogProps(type, overrides)} />);
}

const panel = () => screen.getByTestId('instruction-panel');
const generate = (intent: string) => act(() => instructionPanel().onAiGenerate(intent));

beforeEach(() => {
  vi.resetAllMocks();
  resetKit();
  vi.spyOn(console, 'error').mockImplementation(() => undefined);
  installFakeServer();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('AgentConfigEditDialog: prompt generation', () => {
  it('streams the generated prompt into the draft, replacing the old text with the first chunk', async () => {
    fetchMock.mockImplementation(async () =>
      stream(sse({ type: 'content', data: 'Hello' }), sse({ type: 'content', data: ' world' }), sse({ type: 'done' })),
    );
    show('instruction');

    await generate('make it polite');

    expect(panel()).toHaveAttribute('data-prompt', 'Hello world');
    expect(panel()).toHaveAttribute('data-generating', 'false');
    expect(kit.toast).not.toHaveBeenCalled();
    const [call] = requests('/user-agents/generate-prompt');
    expect(bodyOf(call)).toEqual({
      intent: 'make it polite',
      locale: navigator.language || 'en-US',
      current_prompt: 'Be brief',
    });
  });

  it('sends the prompt as it stands on screen, not as it was when the dialog opened', async () => {
    fetchMock.mockImplementation(async () => stream(sse({ type: 'content', data: 'Done' })));
    show('instruction');
    fireEvent.click(screen.getByRole('button', { name: 'type-prompt' }));

    await generate('make it polite');

    expect(bodyOf(requests('/user-agents/generate-prompt')[0])).toMatchObject({ current_prompt: 'Answer in French' });
  });

  it('shows the generating state until the request is answered', async () => {
    const answer = deferred<Response>();
    fetchMock.mockImplementation(() => answer.promise);
    show('instruction');

    let pending: Promise<void> = Promise.resolve();
    act(() => {
      pending = instructionPanel().onAiGenerate('make it polite');
    });
    expect(panel()).toHaveAttribute('data-generating', 'true');

    await act(async () => {
      answer.resolve(stream(sse({ type: 'content', data: 'Done' })));
      await pending;
    });
    expect(panel()).toHaveAttribute('data-generating', 'false');
  });

  it('reads an event that arrives split over two chunks and skips lines that are not data events', async () => {
    const event = sse({ type: 'content', data: 'Whole' });
    fetchMock.mockImplementation(async () => stream(': ping\n\n', event.slice(0, 12), event.slice(12)));
    show('instruction');

    await generate('x');

    expect(panel()).toHaveAttribute('data-prompt', 'Whole');
    expect(console.error).not.toHaveBeenCalled();
  });

  it('skips a malformed event and keeps the text so far', async () => {
    fetchMock.mockImplementation(async () =>
      stream(sse({ type: 'content', data: 'Kept' }), 'data: {not json\n\n', sse({ type: 'content', data: ' going' })),
    );
    show('instruction');

    await generate('x');

    expect(panel()).toHaveAttribute('data-prompt', 'Kept going');
  });

  it('keeps the draft when the model sends a chunk without text', async () => {
    fetchMock.mockImplementation(async () => stream(sse({ type: 'content', data: '' })));
    show('instruction');

    await generate('x');

    expect(panel()).toHaveAttribute('data-prompt', 'Be brief');
  });

  it('does not call the server for a blank intent', async () => {
    show('instruction');

    await generate('   ');

    expect(requests('/user-agents/generate-prompt')).toHaveLength(0);
  });

  it('tells the user the model provider is missing when the server answers 422', async () => {
    fetchMock.mockImplementation(async () => json({ detail: 'No provider' }, 422));
    show('instruction');

    await generate('x');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'aiGenerateConfigMissing',
      description: 'No provider',
      variant: 'destructive',
    });
    expect(panel()).toHaveAttribute('data-prompt', 'Be brief');
  });

  it('names no cause when the 422 detail is not text', async () => {
    fetchMock.mockImplementation(async () => json({ detail: [{ loc: ['body'] }] }, 422));
    show('instruction');

    await generate('x');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'aiGenerateConfigMissing',
      description: undefined,
      variant: 'destructive',
    });
  });

  it('shows no second notice when a risk rule held the text, which already told the user', async () => {
    fetchMock.mockImplementation(async () => json({ detail: { code: 'risk_held' } }, 400));
    kit.riskHeld.mockResolvedValue(new Error('held'));
    show('instruction');

    await generate('x');

    expect(kit.toast).not.toHaveBeenCalled();
    expect(panel()).toHaveAttribute('data-generating', 'false');
  });

  it('reports an error event of the stream', async () => {
    fetchMock.mockImplementation(async () => stream(sse({ type: 'error', error: 'Model overloaded' })));
    show('instruction');

    await generate('x');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'aiGenerateFailed',
      description: 'Model overloaded',
      variant: 'destructive',
    });
  });

  it('names no cause when the error event carries no text', async () => {
    fetchMock.mockImplementation(async () => stream(sse({ type: 'error', error: { code: 500 } })));
    show('instruction');

    await generate('x');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({
      title: 'aiGenerateFailed',
      description: undefined,
      variant: 'destructive',
    });
  });

  it.each([
    ['answers with a server error', async () => json({ detail: 'boom' }, 500)],
    ['cannot be reached', async () => Promise.reject(new TypeError('Failed to fetch'))],
  ])('reports it when the server %s, instead of ending quietly', async (_name, respond) => {
    fetchMock.mockImplementation(respond);
    show('instruction');

    await generate('x');

    expect(kit.toast).toHaveBeenCalledExactlyOnceWith({ title: 'aiGenerateFailed', variant: 'destructive' });
    expect(panel()).toHaveAttribute('data-generating', 'false');
  });
});

describe('AgentConfigEditDialog: version history', () => {
  const entries = [
    { id: 'h3', version: 3, systemPrompt: 'c', createdAt: '2026-03-01' },
    { id: 'h2', version: 2, systemPrompt: 'b', createdAt: '2026-02-01' },
  ];

  it('loads the history of a saved agent on the instruction card', async () => {
    fetchMock.mockImplementation(async () => json({ data: entries }));
    show('instruction', { agentId: 'agent-7' });

    await waitFor(() => expect(panel()).toHaveAttribute('data-history', '3,2'));
    expect(requests('/user-agents/agent-7/history')).toHaveLength(1);
  });

  it('asks for no history of an unsaved agent or on any other card', () => {
    const { unmount } = show('instruction');
    unmount();
    show('skills', { agentId: 'agent-7' });

    expect(requests('/history')).toHaveLength(0);
  });

  it('keeps an empty history when the answer carries none', async () => {
    const answer = watched(json({ detail: 'Agent not found' }, 404));
    fetchMock.mockImplementation(async () => answer.response);
    show('instruction', { agentId: 'agent-7' });

    await act(answer.settled);

    expect(panel()).toHaveAttribute('data-history', '');
  });

  it('shows an empty history when the request fails', async () => {
    fetchMock.mockImplementation(async () => Promise.reject(new TypeError('Failed to fetch')));
    show('instruction', { agentId: 'agent-7' });

    await waitFor(() => expect(console.error).toHaveBeenCalled());
    expect(panel()).toHaveAttribute('data-history', '');
  });
});
