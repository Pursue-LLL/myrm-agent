import React, { useRef, useEffect, useState } from 'react';
import Editor, { useMonaco } from '@monaco-editor/react';
import { useTheme } from 'next-themes';
import { Loader2, History } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Button } from '@/components/primitives/button';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/primitives/dropdown-menu';
import { formatDistanceToNow } from 'date-fns';

import type { editor } from 'monaco-editor';

interface ProfileHistory {
  id: string;
  version: number;
  systemPrompt: string;
  createdAt: string;
}

interface SmartPromptEditorProps {
  value: string;
  onChange: (val: string) => void;
  onAiGenerate?: (prompt: string) => void;
  history?: ProfileHistory[];
  onRestoreHistory?: (history: ProfileHistory) => void;
  readonly?: boolean;
  className?: string;
  isGenerating?: boolean;
}

export const SmartPromptEditor: React.FC<SmartPromptEditorProps> = ({
  value,
  onChange,
  onAiGenerate,
  history = [],
  onRestoreHistory,
  readonly = false,
  className,
  isGenerating = false,
}) => {
  const t = useTranslations('agent.configEditor');
  const { resolvedTheme } = useTheme();
  const monaco = useMonaco();
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const [aiPrompt, setAiPrompt] = useState('');
  const [showAiInput, setShowAiInput] = useState(false);

  // Configure Monaco when it loads
  useEffect(() => {
    if (monaco) {
      // Register custom variables completion
      const disposable = monaco.languages.registerCompletionItemProvider('markdown', {
        triggerCharacters: ['{'],
        provideCompletionItems: (model, position) => {
          const textUntilPosition = model.getValueInRange({
            startLineNumber: position.lineNumber,
            startColumn: 1,
            endLineNumber: position.lineNumber,
            endColumn: position.column,
          });

          // Check if typing {{
          if (textUntilPosition.endsWith('{{')) {
            const range = new monaco.Range(position.lineNumber, position.column, position.lineNumber, position.column);
            const suggestions = [
              {
                label: 'user_name',
                kind: monaco.languages.CompletionItemKind.Variable,
                insertText: 'user_name}}',
                detail: t('vars.userName'),
                range,
              },
              {
                label: 'current_time',
                kind: monaco.languages.CompletionItemKind.Variable,
                insertText: 'current_time}}',
                detail: t('vars.currentTime'),
                range,
              },
              {
                label: 'current_date',
                kind: monaco.languages.CompletionItemKind.Variable,
                insertText: 'current_date}}',
                detail: t('vars.currentDate'),
                range,
              },
              {
                label: 'os_info',
                kind: monaco.languages.CompletionItemKind.Variable,
                insertText: 'os_info}}',
                detail: t('vars.osInfo'),
                range,
              },
            ];
            return { suggestions };
          }
          return { suggestions: [] };
        },
      });

      return () => {
        disposable.dispose();
      };
    }
  }, [monaco, t]);

  // Cleanup editor instance on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (editorRef.current) {
        editorRef.current.dispose();
      }
    };
  }, []);

  const handleEditorDidMount = (editor: editor.IStandaloneCodeEditor) => {
    editorRef.current = editor;
  };

  const handleAiSubmit = () => {
    if (!aiPrompt.trim() || !onAiGenerate) return;
    onAiGenerate(aiPrompt);
    setShowAiInput(false);
    setAiPrompt('');
  };

  return (
    <div className={cn('flex flex-col border rounded-full overflow-hidden bg-background', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-3 py-2 border-b bg-muted/30">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-muted-foreground">{t('systemPromptLabel')}</span>
          {isGenerating && <Loader2 className="w-3 h-3 animate-spin text-primary" />}
        </div>

        <div className="flex items-center gap-2">
          {!readonly && onAiGenerate && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs gap-1.5 text-blue-600 hover:text-blue-700 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-950"
              onClick={() => setShowAiInput(!showAiInput)}
              disabled={isGenerating}
            >
              <IconGlow className="w-3.5 h-3.5" />
              {t('aiAssist')}
            </Button>
          )}

          {!readonly && history.length > 0 && onRestoreHistory && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="sm" className="h-7 text-xs gap-1.5">
                  <History className="w-3.5 h-3.5" />
                  {t('history')}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                {history.map((h) => (
                  <DropdownMenuItem
                    key={h.id}
                    className="flex flex-col items-start py-2 cursor-pointer"
                    onClick={() => onRestoreHistory(h)}
                  >
                    <div className="flex items-center justify-between w-full">
                      <span className="font-medium text-xs">v{h.version}</span>
                      <span className="text-[10px] text-muted-foreground">
                        {formatDistanceToNow(new Date(h.createdAt), { addSuffix: true })}
                      </span>
                    </div>
                    <span className="text-xs text-muted-foreground line-clamp-1 mt-1">{h.systemPrompt}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </div>
      </div>

      {/* AI Input Panel */}
      {showAiInput && (
        <div className="p-3 border-b bg-blue-50/50 dark:bg-blue-950/20 flex gap-2 items-start animate-in slide-in-from-top-2">
          <textarea
            value={aiPrompt}
            onChange={(e) => setAiPrompt(e.target.value)}
            placeholder={t('aiPromptPlaceholder')}
            className="flex-1 min-h-[60px] text-sm p-2 rounded border bg-background resize-none focus:outline-none focus:ring-1 focus:ring-blue-500"
            onKeyDown={(e) => {
              if (e.nativeEvent.isComposing) return;
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleAiSubmit();
              }
            }}
          />
          <Button size="sm" className="shrink-0" onClick={handleAiSubmit} disabled={!aiPrompt.trim() || isGenerating}>
            {t('generate')}
          </Button>
        </div>
      )}

      {/* Editor */}
      <div className="relative flex-1 min-h-[200px]">
        <Editor
          height="100%"
          language="markdown"
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          value={value}
          onChange={(val) => onChange(val || '')}
          onMount={handleEditorDidMount}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'off',
            glyphMargin: false,
            folding: true,
            lineDecorationsWidth: 0,
            lineNumbersMinChars: 0,
            wordWrap: 'on',
            readOnly: readonly || isGenerating,
            padding: { top: 12, bottom: 12 },
            fontSize: 13,
            fontFamily: 'var(--font-mono)',
            scrollBeyondLastLine: false,
            renderLineHighlight: 'none',
            hideCursorInOverviewRuler: true,
            overviewRulerBorder: false,
            scrollbar: {
              vertical: 'hidden',
              horizontal: 'hidden',
            },
          }}
        />
        {isGenerating && (
          <div className="absolute inset-0 bg-background/50 backdrop-blur-[1px] flex items-center justify-center z-10">
            <div className="flex items-center gap-2 px-4 py-2 rounded-full bg-background border">
              <IconGlow className="w-4 h-4 text-blue-500 animate-pulse" />
              <span className="text-sm font-medium">{t('generating')}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
