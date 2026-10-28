/** @vitest-environment jsdom */
import React from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

interface EditorProps {
  value?: string;
  language?: string;
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: unknown, monaco: unknown) => void;
  options?: { readOnly?: boolean };
}

const { fakeEditor, fakeMonaco, provider, registerCompletionItemProvider } = vi.hoisted(() => {
  const provider = { dispose: vi.fn() };
  const registerCompletionItemProvider = vi.fn((_language: string, _source: unknown) => provider);
  class Range {
    constructor(
      public startLineNumber: number,
      public startColumn: number,
      public endLineNumber: number,
      public endColumn: number,
    ) {}
  }
  const fakeMonaco = {
    Range,
    languages: { registerCompletionItemProvider, CompletionItemKind: { Variable: 6 } },
  };
  const fakeEditor = { dispose: vi.fn() };
  return { fakeEditor, fakeMonaco, provider, registerCompletionItemProvider };
});

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoEditor: (props: EditorProps) => {
    const { onMount } = props;
    React.useEffect(() => {
      onMount?.(fakeEditor, fakeMonaco);
    }, [onMount]);
    return <textarea data-testid="monaco" value={props.value} readOnly />;
  },
}));

import { SmartPromptEditor } from '../SmartPromptEditor';

interface CompletionSource {
  triggerCharacters: string[];
  provideCompletionItems: (
    model: { getValueInRange: () => string },
    position: { lineNumber: number; column: number },
  ) => { suggestions: { label: string; insertText: string; detail: string }[] };
}

function registeredSource(): CompletionSource {
  const [, source] = registerCompletionItemProvider.mock.calls[0];
  return source as CompletionSource;
}

function suggestionsAfter(textBeforeCursor: string) {
  return registeredSource().provideCompletionItems(
    { getValueInRange: () => textBeforeCursor },
    { lineNumber: 1, column: textBeforeCursor.length + 1 },
  ).suggestions;
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe('SmartPromptEditor variable completion', () => {
  it('registers one markdown completion provider triggered by "{"', () => {
    render(<SmartPromptEditor value="" onChange={vi.fn()} />);

    expect(registerCompletionItemProvider).toHaveBeenCalledTimes(1);
    expect(registerCompletionItemProvider.mock.calls[0][0]).toBe('markdown');
    expect(registeredSource().triggerCharacters).toEqual(['{']);
  });

  it('offers the four prompt variables once "{{" has been typed', () => {
    render(<SmartPromptEditor value="" onChange={vi.fn()} />);

    const suggestions = suggestionsAfter('You are {{');

    expect(suggestions.map((s) => s.label)).toEqual(['user_name', 'current_time', 'current_date', 'os_info']);
    expect(suggestions.map((s) => s.insertText)).toEqual([
      'user_name}}',
      'current_time}}',
      'current_date}}',
      'os_info}}',
    ]);
    expect(suggestions.map((s) => s.detail)).toEqual([
      'vars.userName',
      'vars.currentTime',
      'vars.currentDate',
      'vars.osInfo',
    ]);
  });

  it('offers nothing after a single "{" or ordinary text', () => {
    render(<SmartPromptEditor value="" onChange={vi.fn()} />);

    expect(suggestionsAfter('You are {')).toEqual([]);
    expect(suggestionsAfter('You are')).toEqual([]);
  });

  it('removes the provider when the editor goes away', () => {
    const { unmount } = render(<SmartPromptEditor value="" onChange={vi.fn()} />);
    expect(provider.dispose).not.toHaveBeenCalled();

    unmount();

    expect(provider.dispose).toHaveBeenCalledTimes(1);
  });

  it('shows the prompt text it was given', () => {
    render(<SmartPromptEditor value="Be brief." onChange={vi.fn()} />);

    expect(screen.getByTestId('monaco')).toHaveProperty('value', 'Be brief.');
  });
});
