/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';

const { getMountedEditor, setMountedEditor, getMountedMonaco, setMountedMonaco } = vi.hoisted(() => {
  let editorRef: unknown = null;
  let monacoRef: unknown = null;
  return {
    getMountedEditor: () => editorRef,
    setMountedEditor: (e: unknown) => {
      editorRef = e;
    },
    getMountedMonaco: () => monacoRef,
    setMountedMonaco: (m: unknown) => {
      monacoRef = m;
    },
  };
});

vi.mock('@/components/features/app-shell/lazy-monaco-editor', () => ({
  LazyMonacoEditor: (props: {
    value: string;
    onChange?: (val: string) => void;
    onMount?: (ed: unknown, monaco: unknown) => void;
  }) => {
    React.useEffect(() => {
      const mockModel = {
        getValueInRange: vi.fn((range: { selectedText?: string }) => (range.selectedText ? range.selectedText : '')),
      };
      const mockEditor = {
        addCommand: vi.fn(),
        onDidScrollChange: vi.fn(() => ({ dispose: vi.fn() })),
        getSelection: vi.fn(() => ({
          startLineNumber: 1,
          startColumn: 1,
          endLineNumber: 1,
          endColumn: 1,
          isEmpty: () => true,
        })),
        getModel: vi.fn(() => mockModel),
        executeEdits: vi.fn(),
        pushUndoStop: vi.fn(),
        focus: vi.fn(),
        setSelection: vi.fn(),
        getLayoutInfo: vi.fn(() => ({ height: 400 })),
        getScrollHeight: vi.fn(() => 800),
      };
      const mockMonacoObj = {
        KeyMod: { CtrlCmd: 2048 },
        KeyCode: { KeyS: 49, KeyB: 32, KeyI: 39, KeyK: 41 },
        Range: class {
          startLineNumber: number;
          startColumn: number;
          endLineNumber: number;
          endColumn: number;
          constructor(sl: number, sc: number, el: number, ec: number) {
            this.startLineNumber = sl;
            this.startColumn = sc;
            this.endLineNumber = el;
            this.endColumn = ec;
          }
        },
      };
      setMountedEditor(mockEditor);
      setMountedMonaco(mockMonacoObj);
      props.onMount?.(mockEditor, mockMonacoObj);
    }, [props]);

    return (
      <div data-testid="mock-monaco-editor">
        <textarea
          data-testid="mock-monaco-textarea"
          value={props.value}
          onChange={(e) => props.onChange?.(e.target.value)}
        />
      </div>
    );
  },
}));

// Mock MarkdownContent correctly with alias
vi.mock('@/components/features/message-box/MarkdownContent', () => ({
  default: ({ content }: { content: string }) => (
    <div data-testid="mock-markdown-content">{content}</div>
  ),
}));

// Mock useIsMobile hook
let isMobileValue = false;
vi.mock('@/hooks/ui/useMediaQuery', () => ({
  useIsMobile: () => isMobileValue,
}));

import { WikiMarkdownEditor } from '../WikiMarkdownEditor';

interface MockEditorShape {
  addCommand: ReturnType<typeof vi.fn>;
  executeEdits: ReturnType<typeof vi.fn>;
}

describe('WikiMarkdownEditor Component Suite', () => {
  beforeEach(() => {
    isMobileValue = false;
    setMountedEditor(null);
    setMountedMonaco(null);
  });

  afterEach(() => {
    delete (window as unknown as { __wikiMarkdownEditor?: unknown }).__wikiMarkdownEditor;
    delete (window as unknown as { monaco?: unknown }).monaco;
  });

  it('renders dual-pane layout in desktop view', () => {
    const handleChange = vi.fn();
    render(
      <WikiMarkdownEditor
        value="# Title\nHello world"
        onChange={handleChange}
        placeholder="Enter wiki content..."
      />,
    );

    expect(screen.getByTestId('mock-monaco-editor')).toBeDefined();
    expect(screen.getByTestId('wiki-markdown-preview')).toBeDefined();
    expect(screen.getByTestId('mock-markdown-content')).toBeDefined();
    expect(screen.getByTestId('mock-markdown-content').textContent).toContain('# Title');
  });

  it('exposes window.__wikiMarkdownEditor and window.monaco on mount, and cleans up on unmount', () => {
    const { unmount } = render(
      <WikiMarkdownEditor value="content" onChange={vi.fn()} />,
    );

    expect((window as unknown as { __wikiMarkdownEditor?: unknown }).__wikiMarkdownEditor).toBeDefined();
    expect((window as unknown as { monaco?: unknown }).monaco).toBeDefined();

    unmount();
    expect((window as unknown as { __wikiMarkdownEditor?: unknown }).__wikiMarkdownEditor).toBeUndefined();
  });

  it('registers keyboard shortcuts (Cmd+S, Cmd+B, Cmd+I, Cmd+K) on mount', () => {
    const onSave = vi.fn();
    render(<WikiMarkdownEditor value="content" onChange={vi.fn()} onSaveShortcut={onSave} />);

    const editor = getMountedEditor() as MockEditorShape | null;
    expect(editor?.addCommand).toHaveBeenCalledTimes(4);
  });

  it('applies previewTransform when provided (MCP App / Sandpack artifact support)', () => {
    const transform = vi.fn((source: string) => `TRANSFORMED: ${source}`);
    render(
      <WikiMarkdownEditor
        value="raw input"
        onChange={vi.fn()}
        previewTransform={transform}
      />,
    );

    expect(transform).toHaveBeenCalledWith('raw input');
    expect(screen.getByTestId('mock-markdown-content').textContent).toBe('TRANSFORMED: raw input');
  });

  it('supports mobile mode tab switching between edit and preview', () => {
    isMobileValue = true;
    render(<WikiMarkdownEditor value="mobile content" onChange={vi.fn()} />);

    // Mobile tabs present
    const editTab = screen.getByRole('button', { name: /edit/i });
    const previewTab = screen.getByRole('button', { name: /preview/i });
    expect(editTab).toBeDefined();
    expect(previewTab).toBeDefined();

    // Switch to preview mode
    fireEvent.click(previewTab);
    expect(screen.getByTestId('wiki-markdown-preview').parentElement).toBeDefined();

    // Switch back to edit mode
    fireEvent.click(editTab);
    expect(screen.getByTestId('mock-monaco-editor')).toBeDefined();
  });

  it('executes toolbar actions (bold, italic, wikilink, codeblock, quote, table) via Monaco executeEdits', () => {
    render(<WikiMarkdownEditor value="" onChange={vi.fn()} />);

    const editor = getMountedEditor() as MockEditorShape | null;

    // Bold action
    const boldBtn = screen.getByRole('button', { name: /加粗/ });
    fireEvent.click(boldBtn);
    expect(editor?.executeEdits).toHaveBeenCalledWith('toolbar-action', expect.arrayContaining([
      expect.objectContaining({ text: '**粗体文本**' }),
    ]));

    // Italic action
    const italicBtn = screen.getByRole('button', { name: /斜体/ });
    fireEvent.click(italicBtn);
    expect(editor?.executeEdits).toHaveBeenCalledWith('toolbar-action', expect.arrayContaining([
      expect.objectContaining({ text: '*斜体文本*' }),
    ]));

    // Wiki 双链 action
    const wikilinkBtn = screen.getByRole('button', { name: /Wiki 双链/ });
    fireEvent.click(wikilinkBtn);
    expect(editor?.executeEdits).toHaveBeenCalledWith('toolbar-action', expect.arrayContaining([
      expect.objectContaining({ text: '[[页面名称]]' }),
    ]));

    // Codeblock action
    const codeBtn = screen.getByRole('button', { name: /代码块/ });
    fireEvent.click(codeBtn);
    expect(editor?.executeEdits).toHaveBeenCalledWith('toolbar-action', expect.arrayContaining([
      expect.objectContaining({ text: '`代码`' }),
    ]));

    // Table action
    const tableBtn = screen.getByRole('button', { name: /插入表格/ });
    fireEvent.click(tableBtn);
    expect(editor?.executeEdits).toHaveBeenCalledWith('toolbar-action', expect.arrayContaining([
      expect.objectContaining({ text: expect.stringContaining('| 标题 1 | 标题 2 |') }),
    ]));
  });
});
