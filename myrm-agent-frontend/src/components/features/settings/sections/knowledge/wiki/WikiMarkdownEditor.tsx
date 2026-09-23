'use client';

import { useDeferredValue, useState, useRef, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import { Button } from '@/components/primitives/button';
import { IconEdit, IconEye } from '@/components/features/icons/PremiumIcons';
import MarkdownContent from '@/components/features/message-box/MarkdownContent';
import { LazyMonacoEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import { WikiEditorToolbar, type ToolbarAction } from './WikiEditorToolbar';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';
import { cn } from '@/lib/utils/classnameUtils';
import type { editor, IDisposable } from 'monaco-editor';
import type { Monaco } from '@monaco-editor/react';

interface WikiMarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  /** Optional transform applied to the preview source (e.g. strip YAML frontmatter). */
  previewTransform?: (source: string) => string;
  onSaveShortcut?: () => void;
  /** Unique suffix used to scope preview heading anchor ids. */
  messageIdSuffix: string;
  className?: string;
}

export function WikiMarkdownEditor({
  value,
  onChange,
  placeholder,
  previewTransform,
  onSaveShortcut,
  messageIdSuffix,
  className,
}: WikiMarkdownEditorProps) {
  const t = useTranslations('settings.wiki.editor');
  const { resolvedTheme } = useTheme();
  const isMobile = useIsMobile();
  const [mobileMode, setMobileMode] = useState<'edit' | 'preview'>('edit');

  const editorInstanceRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const previewContainerRef = useRef<HTMLDivElement>(null);
  const scrollDisposableRef = useRef<IDisposable | null>(null);

  // Split rendering load: only the source pane changes on every keystroke,
  // the preview renders with the deferred value so React can yield to input.
  const deferredValue = useDeferredValue(value);
  const previewSource = previewTransform ? previewTransform(deferredValue) : deferredValue;

  const handleEditorDidMount = (editorInstance: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    editorInstanceRef.current = editorInstance;

    if (onSaveShortcut) {
      editorInstance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        onSaveShortcut();
      });
    }

    // Bind scroll synchronization from Monaco editor to preview container
    scrollDisposableRef.current?.dispose();
    scrollDisposableRef.current = editorInstance.onDidScrollChange((e) => {
      if (isMobile) {
        return;
      }
      const container = previewContainerRef.current;
      if (!container) {
        return;
      }

      requestAnimationFrame(() => {
        const layout = editorInstance.getLayoutInfo();
        const scrollHeight = editorInstance.getScrollHeight() - layout.height;
        if (scrollHeight <= 0) {
          return;
        }

        const ratio = Math.max(0, Math.min(1, e.scrollTop / scrollHeight));
        const targetScrollTop = ratio * (container.scrollHeight - container.clientHeight);
        container.scrollTop = targetScrollTop;
      });
    });

    // Expose the editor for E2E to drive programmatic input
    if (typeof window !== 'undefined') {
      window.__wikiMarkdownEditor = editorInstance;
    }
  };

  // Ensure Monaco reference and scroll listeners are cleanly disposed on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && window.__wikiMarkdownEditor === editorInstanceRef.current) {
        delete window.__wikiMarkdownEditor;
      }
      if (scrollDisposableRef.current) {
        scrollDisposableRef.current.dispose();
        scrollDisposableRef.current = null;
      }
      editorInstanceRef.current = null;
    };
  }, []);

  const handleToolbarAction = useCallback((action: ToolbarAction) => {
    const editorInstance = editorInstanceRef.current;
    if (!editorInstance) {
      return;
    }

    const selection = editorInstance.getSelection();
    const model = editorInstance.getModel();
    if (!selection || !model) {
      return;
    }

    const selectedText = model.getValueInRange(selection);
    let replaceText = '';

    switch (action) {
      case 'bold':
        replaceText = selectedText ? `**${selectedText}**` : '**粗体文本**';
        break;
      case 'italic':
        replaceText = selectedText ? `*${selectedText}*` : '*斜体文本*';
        break;
      case 'h2':
        replaceText = selectedText ? `\n## ${selectedText}\n` : '\n## 二级标题\n';
        break;
      case 'code':
        if (selectedText.includes('\n')) {
          replaceText = `\n\`\`\`markdown\n${selectedText}\n\`\`\`\n`;
        } else {
          replaceText = selectedText ? `\`${selectedText}\`` : '`代码`';
        }
        break;
      case 'quote':
        replaceText = selectedText ? `\n> ${selectedText}\n` : '\n> 引用文本\n';
        break;
      case 'bullet':
        replaceText = selectedText ? `\n- ${selectedText}\n` : '\n- 列表项\n';
        break;
      case 'todo':
        replaceText = selectedText ? `\n- [ ] ${selectedText}\n` : '\n- [ ] 待办任务\n';
        break;
      case 'wikilink':
        replaceText = selectedText ? `[[${selectedText}]]` : '[[页面名称]]';
        break;
      case 'table':
        replaceText = '\n| 标题 1 | 标题 2 |\n| --- | --- |\n| 内容 1 | 内容 2 |\n';
        break;
    }

    editorInstance.executeEdits('toolbar-action', [
      {
        range: selection,
        text: replaceText,
        forceMoveMarkers: true,
      },
    ]);
    editorInstance.focus();
  }, []);

  const editorPane = (
    <div
      className={cn(
        'min-w-0 min-h-0 flex-1 border rounded-md overflow-hidden bg-background flex flex-col',
        isMobile && mobileMode !== 'edit' && 'hidden',
      )}
    >
      <WikiEditorToolbar onAction={handleToolbarAction} />
      <div className="flex-1 min-h-0">
        <LazyMonacoEditor
          height="100%"
          language="markdown"
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          value={value}
          onChange={(val) => onChange(val ?? '')}
          onMount={handleEditorDidMount}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'off',
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 0,
            wordWrap: 'on',
            placeholder,
            padding: { top: 12, bottom: 12 },
            fontSize: 13,
            fontFamily: 'var(--font-mono)',
            scrollBeyondLastLine: false,
            renderLineHighlight: 'none',
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            scrollbar: {
              vertical: 'visible',
              horizontal: 'hidden',
            },
            automaticLayout: true,
          }}
        />
      </div>
    </div>
  );

  const previewPane = (
    <div
      ref={previewContainerRef}
      data-testid="wiki-markdown-preview"
      className={cn(
        'min-w-0 min-h-0 flex-1 border rounded-md overflow-y-auto bg-background p-4',
        isMobile && mobileMode !== 'preview' && 'hidden',
      )}
    >
      <MarkdownContent
        content={previewSource}
        sources={[]}
        messageId={`wiki-preview-${messageIdSuffix}`}
        isStreaming={false}
      />
    </div>
  );

  return (
    <div className={cn('flex flex-col min-h-0 flex-1 w-full gap-2', className)}>
      {isMobile && (
        <div className="flex gap-2">
          <Button
            type="button"
            size="sm"
            variant={mobileMode === 'edit' ? 'default' : 'outline'}
            onClick={() => setMobileMode('edit')}
          >
            <IconEdit className="w-4 h-4 mr-1.5" />
            {t('edit')}
          </Button>
          <Button
            type="button"
            size="sm"
            variant={mobileMode === 'preview' ? 'default' : 'outline'}
            onClick={() => setMobileMode('preview')}
          >
            <IconEye className="w-4 h-4 mr-1.5" />
            {t('preview')}
          </Button>
        </div>
      )}
      <div className={cn('min-h-0 flex-1 gap-3', isMobile ? 'flex' : 'grid grid-cols-2')}>
        {editorPane}
        {previewPane}
      </div>
    </div>
  );
}
