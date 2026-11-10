/**
 * The "Instruction" tab of the agent edit dialog.
 *
 * Real scenario: the user decides whether the global instructions apply, edits the agent's own system prompt, restores an
 * earlier version, and - when they only see the agent, not own it - is told the prompt is hidden and can ask to reveal it.
 * The Monaco-based editor is replaced by a textarea stub; everything the panel hands to it is checked.
 */
import { fireEvent, render, screen } from '@testing-library/react';
import { useTranslations } from 'next-intl';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { HIDDEN_SYSTEM_PROMPT } from '@/services/agent';

import { InstructionPanel } from '../InstructionPanel';
import type { SmartPromptEditor } from '../SmartPromptEditor';

type EditorProps = ComponentProps<typeof SmartPromptEditor>;

const editor = vi.hoisted(() => ({ props: undefined as EditorProps | undefined }));

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'en'));
vi.mock('next/dynamic', () => ({
  default: () =>
    function EditorStub(props: EditorProps) {
      editor.props = props;
      return (
        <textarea aria-label="prompt editor" value={props.value} onChange={(e) => props.onChange(e.target.value)} />
      );
    },
}));
vi.mock('../HarnessAblationLeverageTooltip', () => ({ default: () => <div data-testid="ablation-tooltip" /> }));

const handlers = {
  setLocalPrompt: vi.fn<(value: string) => void>(),
  setLocalUseGlobalInstruction: vi.fn<(value: boolean) => void>(),
  onShowSystemPrompt: vi.fn<() => void>(),
  onAiGenerate: vi.fn<(intent: string) => Promise<void>>(async () => undefined),
};

function Panel(props: Partial<ComponentProps<typeof InstructionPanel>>) {
  const t = useTranslations('agent.configEditor');
  const tCommon = useTranslations('common');
  return (
    <InstructionPanel
      localPrompt="Be brief"
      localUseGlobalInstruction
      isSystemPromptHidden={false}
      loadingSystemPrompt={false}
      isGeneratingAi={false}
      history={[]}
      {...handlers}
      {...props}
      t={t}
      tCommon={tCommon}
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  editor.props = undefined;
});

describe('InstructionPanel global instruction', () => {
  it.each([true, false])('shows the switch as %s and reports flipping it', (current) => {
    render(<Panel localUseGlobalInstruction={current} />);
    expect(screen.getByText('Use Global Instructions')).toBeInTheDocument();
    expect(screen.getByText(/^When enabled, global instructions will be combined/)).toBeInTheDocument();
    const toggle = screen.getByRole('switch');
    expect(toggle).toHaveAttribute('aria-checked', String(current));

    fireEvent.click(toggle);

    expect(handlers.setLocalUseGlobalInstruction).toHaveBeenCalledExactlyOnceWith(!current);
  });

  it('shows the ablation leverage hint', () => {
    render(<Panel />);

    expect(screen.getByTestId('ablation-tooltip')).toBeInTheDocument();
  });
});

describe('InstructionPanel hidden prompt', () => {
  it('tells the viewer the prompt is hidden and offers to reveal it', () => {
    render(<Panel isSystemPromptHidden localPrompt={HIDDEN_SYSTEM_PROMPT} />);

    expect(screen.getByText('System Prompt Hidden')).toBeInTheDocument();
    expect(screen.getByText('Click show button to reveal the complete prompt (owner only)')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Show' }));

    expect(handlers.onShowSystemPrompt).toHaveBeenCalledTimes(1);
  });

  it.each([
    ['the agent is not flagged as hidden', false, HIDDEN_SYSTEM_PROMPT],
    ['the text was replaced by the user', true, 'My own prompt'],
    ['the text was emptied', true, ''],
  ])('says nothing when %s', (_why, hidden, prompt) => {
    render(<Panel isSystemPromptHidden={hidden} localPrompt={prompt} />);

    expect(screen.queryByText('System Prompt Hidden')).toBeNull();
    expect(screen.queryByRole('button', { name: 'Show' })).toBeNull();
  });

  it('disables the button and says it is loading while the prompt is being fetched', () => {
    render(<Panel isSystemPromptHidden localPrompt={HIDDEN_SYSTEM_PROMPT} loadingSystemPrompt />);

    const button = screen.getByRole('button', { name: 'Loading...' });
    expect(button).toBeDisabled();
    expect(screen.queryByRole('button', { name: 'Show' })).toBeNull();

    fireEvent.click(button);

    expect(handlers.onShowSystemPrompt).not.toHaveBeenCalled();
  });
});

describe('InstructionPanel editor', () => {
  const history = [
    { id: 'h1', version: 2, systemPrompt: 'Older prompt', createdAt: '2026-01-02T00:00:00Z' },
    { id: 'h0', version: 1, systemPrompt: '', createdAt: '2026-01-01T00:00:00Z' },
    { id: 'hn', version: 0, systemPrompt: null, createdAt: '2025-12-31T00:00:00Z' },
  ];

  it('hands the editor the draft, the generation state and the history', () => {
    render(<Panel localPrompt="Draft prompt" isGeneratingAi history={history} />);

    expect(screen.getByRole('textbox', { name: 'prompt editor' })).toHaveValue('Draft prompt');
    expect(editor.props).toMatchObject({
      value: 'Draft prompt',
      isGenerating: true,
      history,
      className: 'w-full h-[300px]',
      onAiGenerate: handlers.onAiGenerate,
    });
  });

  it('writes what the user types back as the draft', () => {
    render(<Panel />);

    fireEvent.change(screen.getByRole('textbox', { name: 'prompt editor' }), { target: { value: 'New text' } });

    expect(handlers.setLocalPrompt).toHaveBeenCalledExactlyOnceWith('New text');
  });

  it('restores an earlier version as the draft, an empty one or one saved without a prompt included', () => {
    render(<Panel history={history} />);

    editor.props?.onRestoreHistory?.(history[0]);
    expect(handlers.setLocalPrompt).toHaveBeenLastCalledWith('Older prompt');

    editor.props?.onRestoreHistory?.(history[1]);
    expect(handlers.setLocalPrompt).toHaveBeenLastCalledWith('');

    editor.props?.onRestoreHistory?.(history[2]);
    expect(handlers.setLocalPrompt).toHaveBeenLastCalledWith('');
    expect(handlers.setLocalPrompt).toHaveBeenCalledTimes(3);
  });
});
