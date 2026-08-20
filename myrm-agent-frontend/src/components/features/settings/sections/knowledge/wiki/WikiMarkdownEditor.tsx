'use client';

import { useDeferredValue, useState } from 'react';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import { Button } from '@/components/primitives/button';
import { IconEdit, IconEye } from '@/components/features/icons/PremiumIcons';
import MarkdownContent from '@/components/features/message-box/MarkdownContent';
import { LazyMonacoEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import { useIsMobile } from '@/hooks/ui/useMediaQuery';
import { cn } from '@/lib/utils/classnameUtils';
import type { editor } from 'monaco-editor';
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

  // Split rendering load: only the source pane changes on every keystroke,
  // the preview renders with the deferred value so React can yield to input.
  const deferredValue = useDeferredValue(value);
  const previewSource = previewTransform ? previewTransform(deferredValue) : deferredValue;

  const handleEditorDidMount = (editorInstance: editor.IStandaloneCodeEditor, monaco: Monaco) => {
    if (onSaveShortcut) {
      editorInstance.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => {
        onSaveShortcut();
      });
    }
    // Expose the editor for E2E to drive programmatic input (Monaco ignores
    // synthetic DOM events / execCommand on its hidden textarea).
    if (typeof window !== 'undefined') {
      window.__wikiMarkdownEditor = editorInstance;
    }
  };

  const editorPane = (
    <div
      className={cn(
        'min-w-0 min-h-0 flex-1 border rounded-md overflow-hidden bg-background',
        isMobile && mobileMode !== 'edit' && 'hidden',
      )}
    >
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
  );

  const previewPane = (
    <div
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
