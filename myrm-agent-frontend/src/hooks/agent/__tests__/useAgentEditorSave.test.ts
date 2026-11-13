import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useAgentEditorSave } from '../useAgentEditorSave';

const { toastMock } = vi.hoisted(() => ({ toastMock: vi.fn() }));

vi.mock('@/hooks/shared/useToast', () => ({ toast: toastMock }));
vi.mock('@/services/riskHeldToast', () => ({
  isRiskHeldError: (error: unknown) => (error as { riskHeld?: boolean }).riskHeld === true,
}));

type EditorArg = Parameters<typeof useAgentEditorSave>[0];
type BindingsArg = Parameters<typeof useAgentEditorSave>[1];

const t = (key: string) => key;

function setup(editor: Partial<EditorArg> = {}, bindings: Partial<BindingsArg> = {}) {
  const calls: string[] = [];
  const editorArg: EditorArg = {
    hasChanges: false,
    saving: false,
    isReadonly: false,
    handleSave: vi.fn(async () => {
      calls.push('editor.save');
    }),
    handleStartChat: vi.fn(async () => {
      calls.push('editor.startChat');
    }),
    ...editor,
  };
  const bindingsArg: BindingsArg = {
    dirty: false,
    canSave: true,
    saving: false,
    save: vi.fn(async () => {
      calls.push('bindings.save');
    }),
    ...bindings,
  };
  const view = renderHook(() => useAgentEditorSave(editorArg, bindingsArg, t));
  return { ...view, calls, editorArg, bindingsArg };
}

describe('useAgentEditorSave', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports unsaved and saving state from either source', () => {
    expect(setup().result.current).toMatchObject({ hasChanges: false, saving: false });
    expect(setup({ hasChanges: true }).result.current.hasChanges).toBe(true);
    expect(setup({}, { dirty: true }).result.current.hasChanges).toBe(true);
    expect(setup({ saving: true }).result.current.saving).toBe(true);
    expect(setup({}, { saving: true }).result.current.saving).toBe(true);
  });

  it('ignores a command-binding draft on a read-only agent', async () => {
    const { result, calls } = setup({ isReadonly: true }, { dirty: true });

    expect(result.current.hasChanges).toBe(false);
    await act(() => result.current.handleStartChat());
    expect(calls).toEqual(['editor.startChat']);
  });

  it('saves only the bindings when nothing else changed, skipping the full update', async () => {
    const { result, calls } = setup({}, { dirty: true });

    await act(() => result.current.handleSave());

    expect(calls).toEqual(['bindings.save']);
    expect(toastMock).toHaveBeenCalledWith({ title: 'agent.commandBindings.saved' });
  });

  it('saves the bindings first, then the rest of the configuration, with a single success notice', async () => {
    const { result, calls } = setup({ hasChanges: true }, { dirty: true });

    await act(() => result.current.handleSave());

    expect(calls).toEqual(['bindings.save', 'editor.save']);
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('saves the configuration alone when the bindings are untouched', async () => {
    const { result, calls } = setup({ hasChanges: true });

    await act(() => result.current.handleSave());

    expect(calls).toEqual(['editor.save']);
  });

  it('saves nothing and explains why when a binding is incomplete', async () => {
    const { result, calls } = setup({ hasChanges: true }, { dirty: true, canSave: false });

    await act(() => result.current.handleSave());

    expect(calls).toEqual([]);
    expect(toastMock).toHaveBeenCalledWith({ title: 'agent.commandBindings.fixBeforeSave', variant: 'destructive' });
  });

  it('reports a failed bindings save and stops before the full update', async () => {
    const save = vi.fn().mockRejectedValue(new Error('boom'));
    const { result, calls } = setup({ hasChanges: true }, { dirty: true, save });

    await act(() => result.current.handleSave());

    expect(save).toHaveBeenCalledTimes(1);
    expect(calls).toEqual([]);
    expect(toastMock).toHaveBeenCalledWith({
      title: 'agent.operationFailed',
      description: 'boom',
      variant: 'destructive',
    });
  });

  it('adds no second notice when the refusal has already been shown to the user', async () => {
    const save = vi.fn().mockRejectedValue(Object.assign(new Error('held'), { riskHeld: true }));
    const { result, calls } = setup({ hasChanges: true }, { dirty: true, save });

    await act(() => result.current.handleSave());

    expect(calls).toEqual([]);
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('does not surface an unhandled rejection when the full update fails', async () => {
    const handleSave = vi.fn().mockRejectedValue(new Error('boom'));
    const { result } = setup({ hasChanges: true, handleSave });

    await act(() => result.current.handleSave());

    expect(handleSave).toHaveBeenCalledTimes(1);
  });

  it('starts the chat only after the bindings are saved, without a notice for the page being left', async () => {
    const { result, calls } = setup({}, { dirty: true });

    await act(() => result.current.handleStartChat());

    expect(calls).toEqual(['bindings.save', 'editor.startChat']);
    expect(toastMock).not.toHaveBeenCalled();
  });

  it('does not start the chat when the bindings cannot be saved', async () => {
    const { result, calls } = setup({}, { dirty: true, canSave: false });

    await act(() => result.current.handleStartChat());

    expect(calls).toEqual([]);
  });
});
