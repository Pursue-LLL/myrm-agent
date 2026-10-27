/** @vitest-environment jsdom */
import React, { useState } from 'react';
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

interface MonacoProps {
  defaultValue?: string;
  value?: string;
  path?: string;
  theme?: string;
  saveViewState?: boolean;
  options?: Record<string, unknown> & {
    ariaLabel?: string;
    minimap?: { enabled: boolean };
    stickyScroll?: { enabled: boolean };
    unicodeHighlight?: { ambiguousCharacters: boolean };
  };
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: unknown, monaco: unknown) => void;
}

const { mounted, appTheme } = vi.hoisted(() => ({
  mounted: { props: null as MonacoProps | null },
  appTheme: { resolved: 'light' as string | undefined },
}));

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoEditor: (props: MonacoProps) => {
    mounted.props = props;
    return <div data-testid="monaco" />;
  },
}));
vi.mock('next-themes', () => ({ useTheme: () => ({ resolvedTheme: appTheme.resolved }) }));

import { WorkspaceCodeEditor } from '../WorkspaceCodeEditor';

const LF = 0;

/** Just enough of Monaco to see what the component asks of it. */
function fakeMonaco() {
  return {
    editor: { EndOfLineSequence: { LF, CRLF: 1 } },
    typescript: {
      typescriptDefaults: { setDiagnosticsOptions: vi.fn() },
      javascriptDefaults: { setDiagnosticsOptions: vi.fn() },
    },
  };
}

function fakeEditor(initial: string) {
  let text = initial;
  const model = {
    getValue: () => text,
    setValue: vi.fn((next: string) => {
      text = next;
    }),
    setEOL: vi.fn(),
  };
  const editor = {
    getModel: () => model,
    saveViewState: vi.fn(() => ({ cursor: 'saved' })),
    restoreViewState: vi.fn(),
  };
  return {
    model,
    editor,
    /** What a user does: the model changes first, then Monaco reports the change. */
    type(next: string) {
      text = next;
      mounted.props?.onChange?.(next);
    },
  };
}

function mountEditor(initial: string, monaco = fakeMonaco()) {
  const onChange = vi.fn();
  const view = render(<WorkspaceCodeEditor value={initial} label="notes.md" onChange={onChange} />);
  const fake = fakeEditor(initial);
  act(() => mounted.props?.onMount?.(fake.editor, monaco));
  return { ...fake, monaco, onChange, view };
}

beforeEach(() => {
  mounted.props = null;
  appTheme.resolved = 'light';
});

describe('WorkspaceCodeEditor', () => {
  it('starts from the given text and then owns the text itself', () => {
    render(<WorkspaceCodeEditor value="hello" label="notes.md" onChange={vi.fn()} />);

    expect(mounted.props?.defaultValue).toBe('hello');
    // A controlled `value` would make the wrapper re-apply the whole text as one undoable edit after every change.
    expect(mounted.props).not.toHaveProperty('value');
  });

  it('gives each editor a model of its own, named like the file so Monaco picks the language', () => {
    render(<WorkspaceCodeEditor value="" label="my notes #1.md" onChange={vi.fn()} />);
    const first = mounted.props?.path;
    render(<WorkspaceCodeEditor value="" label="my notes #1.md" onChange={vi.fn()} />);
    const second = mounted.props?.path;

    expect(first).toMatch(/\/my%20notes%20%231\.md$/);
    expect(second).not.toBe(first);
    // View states are kept per path by the wrapper: with throwaway paths they would only pile up.
    expect(mounted.props?.saveViewState).toBe(false);
  });

  it('reports what is typed, and does not hand it back to the editor', () => {
    const { type, model, onChange, view } = mountEditor('hello');

    type('hello!');
    expect(onChange).toHaveBeenCalledExactlyOnceWith('hello!');

    view.rerender(<WorkspaceCodeEditor value="hello!" label="notes.md" onChange={onChange} />);
    expect(model.setValue).not.toHaveBeenCalled();
  });

  it('has the owner hold the typed text before the keystroke is over, so a shortcut right after it sees that text', () => {
    let held = '';
    const Owner = () => {
      const [text, setText] = useState('hello');
      held = text;
      return <WorkspaceCodeEditor value={text} label="notes.md" onChange={setText} />;
    };
    render(<Owner />);
    const fake = fakeEditor('hello');
    act(() => mounted.props?.onMount?.(fake.editor, fakeMonaco()));

    act(() => {
      fake.type('hello!');
      // Not "after act settles": Ctrl+S is handled by the very next event, with whatever the owner holds by then.
      expect(held).toBe('hello!');
    });
  });

  it('replaces the text when the owner changes it, keeping the cursor and scroll where they were', () => {
    const { editor, model, onChange, view } = mountEditor('hello');

    view.rerender(<WorkspaceCodeEditor value="hello, world" label="notes.md" onChange={onChange} />);

    expect(editor.saveViewState).toHaveBeenCalled();
    expect(model.setValue).toHaveBeenCalledExactlyOnceWith('hello, world');
    expect(editor.restoreViewState).toHaveBeenCalledWith({ cursor: 'saved' });
  });

  it('does not report the change its own replacement makes', () => {
    const { model, onChange, view } = mountEditor('hello');
    model.setValue.mockImplementation((next: string) => {
      mounted.props?.onChange?.(next);
    });

    view.rerender(<WorkspaceCodeEditor value="changed" label="notes.md" onChange={onChange} />);

    expect(model.setValue).toHaveBeenCalledTimes(1);
    expect(onChange).not.toHaveBeenCalled();
  });

  it('applies text that arrived while the editor was still loading', () => {
    const onChange = vi.fn();
    const view = render(<WorkspaceCodeEditor value="old" label="notes.md" onChange={onChange} />);
    view.rerender(<WorkspaceCodeEditor value="newer" label="notes.md" onChange={onChange} />);
    const fake = fakeEditor('old');

    act(() => mounted.props?.onMount?.(fake.editor, fakeMonaco()));

    expect(fake.model.setValue).toHaveBeenCalledExactlyOnceWith('newer');
  });

  it('keeps line breaks as \\n, whatever the platform default is, so the text never differs by line ending', () => {
    const { model, onChange, view } = mountEditor('one line');
    expect(model.setEOL).toHaveBeenCalledWith(LF);

    // Replacing a text of one line makes Monaco fall back to the platform default again.
    model.setEOL.mockClear();
    view.rerender(<WorkspaceCodeEditor value="another" label="notes.md" onChange={onChange} />);
    expect(model.setEOL).toHaveBeenCalledWith(LF);
  });

  it('reports to the latest onChange', () => {
    const { type, view } = mountEditor('a');
    const later = vi.fn();

    view.rerender(<WorkspaceCodeEditor value="a" label="notes.md" onChange={later} />);
    type('ab');

    expect(later).toHaveBeenCalledWith('ab');
  });

  it.each([
    ['dark', 'vs-dark'],
    ['light', 'light'],
    [undefined, 'light'],
  ])('follows the app theme (%s)', (resolved, expected) => {
    appTheme.resolved = resolved;

    render(<WorkspaceCodeEditor value="" label="notes.md" onChange={vi.fn()} />);

    expect(mounted.props?.theme).toBe(expected);
  });

  it('behaves as a file editor rather than an IDE', () => {
    render(<WorkspaceCodeEditor value="" label="notes.md" onChange={vi.fn()} />);
    const options = mounted.props?.options;

    expect(options?.ariaLabel).toBe('notes.md');
    expect(options?.minimap?.enabled).toBe(false);
    expect(options?.stickyScroll?.enabled).toBe(false);
    expect(options?.wordWrap).toBe('on');
    // No pop-ups while typing prose or config files.
    expect(options?.quickSuggestions).toBe(false);
    expect(options?.wordBasedSuggestions).toBe('off');
    expect(options?.suggestOnTriggerCharacters).toBe(false);
    expect(options?.parameterHints).toEqual({ enabled: false });
    // Chinese punctuation is not a lookalike to flag, and a stray line separator is left alone, not offered for removal.
    expect(options?.unicodeHighlight?.ambiguousCharacters).toBe(false);
    expect(options?.unusualLineTerminators).toBe('off');
    expect(options?.automaticLayout).toBe(true);
  });

  it('keeps the same options object between renders', () => {
    const view = render(<WorkspaceCodeEditor value="a" label="notes.md" onChange={vi.fn()} />);
    const first = mounted.props?.options;

    view.rerender(<WorkspaceCodeEditor value="b" label="notes.md" onChange={vi.fn()} />);

    expect(mounted.props?.options).toBe(first);
  });

  it('turns off the project-less semantic checks of TypeScript and JavaScript, once per Monaco', () => {
    const monaco = fakeMonaco();
    mountEditor('a', monaco);
    mountEditor('b', monaco);

    for (const defaults of [monaco.typescript.typescriptDefaults, monaco.typescript.javascriptDefaults]) {
      expect(defaults.setDiagnosticsOptions).toHaveBeenCalledExactlyOnceWith(
        expect.objectContaining({ noSemanticValidation: true, noSuggestionDiagnostics: true }),
      );
      // A syntax error is still a real error in a lone file.
      expect(defaults.setDiagnosticsOptions.mock.calls[0][0]).not.toHaveProperty('noSyntaxValidation', true);
    }
  });
});
