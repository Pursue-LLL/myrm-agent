'use client';

/**
 * The code editor of the workspace file preview (Monaco): syntax colours, find and replace, multiple cursors, a
 * reliable undo stack, and smooth editing of files up to the read limit.
 *
 * [INPUT]
 * - value / label / onChange: the text to edit, what the editor is called (the file name, which also tells Monaco
 *   the language), and where typing goes
 * - LazyMonacoEditor from app-shell (POS: loads Monaco on first use, never on the server)
 *
 * [OUTPUT]
 * - WorkspaceCodeEditor: fills its parent; reports each edit once, as the full text with `\n` line breaks
 *
 * [POS]
 * Chosen over the textarea editor on a desktop pointer (see codeEditorSupport). The editor owns the text while it
 * is typed into, so the caret, undo history and scroll position are never disturbed by a re-render. A text that
 * the owner changes (the file was refreshed from disk, the edits were discarded) replaces the editor's text in one
 * step that starts a fresh undo history, with the caret and scroll kept; it is not reported back as an edit.
 * Each mounted editor has a model of its own, so two files with the same name never share text or history.
 * An edit reaches the owner before Monaco's event returns (React would otherwise render it a moment later, outside
 * its own event system), so Ctrl+S, the Save button and closing the file always act on the text on screen.
 * Monaco is a file editor here, not an IDE: no completion pop-ups, no project-less TypeScript semantic errors,
 * and no warnings for the punctuation of other languages.
 */

import React, { memo, useCallback, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { EditorProps, Monaco, OnMount } from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import { LazyMonacoEditor } from '@/components/features/app-shell/lazy-monaco-editor';

interface WorkspaceCodeEditorProps {
  value: string;
  /** What assistive technology announces and what Monaco derives the language from: the name of the file. */
  label: string;
  onChange: (value: string) => void;
}

interface MountedEditor {
  editor: editor.IStandaloneCodeEditor;
  monaco: Monaco;
}

/** Models are told apart by an id, so two editors on files of the same name never meet in one model. */
let nextModelId = 0;

const EDITOR_OPTIONS: EditorProps['options'] = {
  automaticLayout: true,
  minimap: { enabled: false },
  stickyScroll: { enabled: false },
  glyphMargin: false,
  lineNumbersMinChars: 3,
  scrollBeyondLastLine: false,
  wordWrap: 'on',
  fontSize: 12,
  lineHeight: 20,
  fontFamily: 'var(--font-mono)',
  padding: { top: 4, bottom: 4 },
  renderWhitespace: 'selection',
  // Typing prose or a config file should not pop anything up.
  quickSuggestions: false,
  wordBasedSuggestions: 'off',
  suggestOnTriggerCharacters: false,
  parameterHints: { enabled: false },
  // Fullwidth punctuation is not a lookalike to warn about, and a line separator already in the file is left alone
  // instead of being offered for removal.
  unicodeHighlight: { ambiguousCharacters: false, nonBasicASCII: false },
  unusualLineTerminators: 'off',
};

const configuredMonaco = new WeakSet<Monaco>();

/**
 * A file opened on its own has no project around it: "cannot find module" and the like would be noise on every
 * import, so TypeScript and JavaScript keep only their syntax errors.
 */
function configureLanguageServices(monaco: Monaco): void {
  if (configuredMonaco.has(monaco)) {
    return;
  }
  configuredMonaco.add(monaco);
  const diagnostics = { noSemanticValidation: true, noSuggestionDiagnostics: true };
  monaco.typescript.typescriptDefaults.setDiagnosticsOptions(diagnostics);
  monaco.typescript.javascriptDefaults.setDiagnosticsOptions(diagnostics);
}

export const WorkspaceCodeEditor: React.FC<WorkspaceCodeEditorProps> = memo(({ value, label, onChange }) => {
  const [initialText] = useState(value);
  const [modelPath] = useState(() => `inmemory://workspace/${nextModelId++}/${encodeURIComponent(label)}`);
  const options = useMemo(() => ({ ...EDITOR_OPTIONS, ariaLabel: label }), [label]);

  const mounted = useRef<MountedEditor | null>(null);
  const ownerText = useRef(value);
  const ownerOnChange = useRef(onChange);
  // Changes the owner or the set-up make to the text are announced by Monaco like the user's; those are not reported.
  const unreported = useRef(false);

  const withoutReporting = useCallback((change: () => void) => {
    unreported.current = true;
    try {
      change();
    } finally {
      unreported.current = false;
    }
  }, []);

  const applyOwnerText = useCallback(() => {
    const current = mounted.current;
    const model = current?.editor.getModel();
    if (!current || !model || model.getValue() === ownerText.current) {
      return;
    }
    withoutReporting(() => {
      const view = current.editor.saveViewState();
      model.setValue(ownerText.current);
      // A text of a single line makes Monaco fall back to the platform's line break, which on Windows is \r\n.
      model.setEOL(current.monaco.editor.EndOfLineSequence.LF);
      current.editor.restoreViewState(view);
    });
  }, [withoutReporting]);

  // A layout effect runs inside the commit, so no keystroke can land between the render and this check: the owner's
  // text can only differ from the editor's when the owner changed it.
  useLayoutEffect(() => {
    ownerText.current = value;
    ownerOnChange.current = onChange;
    applyOwnerText();
  }, [value, onChange, applyOwnerText]);

  const handleMount = useCallback<OnMount>(
    (codeEditor, monaco) => {
      mounted.current = { editor: codeEditor, monaco };
      configureLanguageServices(monaco);
      // Before anything is typed, so that every later edit carries \n as its line break.
      withoutReporting(() => codeEditor.getModel()?.setEOL(monaco.editor.EndOfLineSequence.LF));
      // The owner's text may have moved on while Monaco was loading.
      applyOwnerText();
    },
    [applyOwnerText, withoutReporting],
  );

  const handleChange = useCallback((text: string | undefined) => {
    if (!unreported.current && text !== undefined) {
      flushSync(() => ownerOnChange.current(text));
    }
  }, []);

  return (
    <div className="workspace-code-editor h-full">
      <LazyMonacoEditor
        defaultValue={initialText}
        path={modelPath}
        saveViewState={false}
        options={options}
        loading={null}
        onMount={handleMount}
        onChange={handleChange}
      />
    </div>
  );
});

WorkspaceCodeEditor.displayName = 'WorkspaceCodeEditor';
