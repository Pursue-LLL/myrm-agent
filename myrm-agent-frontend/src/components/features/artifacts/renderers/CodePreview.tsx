'use client';

import React, { memo, useEffect, useRef, useState, useCallback, useMemo } from 'react';
import { useDebounce } from 'use-debounce';
import { useTheme } from 'next-themes';
import { useTranslations } from 'next-intl';
import Editor from '@monaco-editor/react';
import type { editor } from 'monaco-editor';
import useArtifactPortalStore, { useIsGenerating } from '@/store/useArtifactPortalStore';
import SelectionToolbar from '../portal/SelectionToolbar';

interface CodePreviewProps {
  content: string;
  language?: string;
  artifactId?: string;
}

type MonacoNamespace = typeof import('monaco-editor');

/** 可编辑的代码预览组件 (基于 Monaco Editor)，集成 SelectionToolbar 选中精准编辑。 */
const CodePreview: React.FC<CodePreviewProps> = memo(({ content, language, artifactId }) => {
  const { resolvedTheme } = useTheme();
  const t = useTranslations('artifacts');
  const [editableContent, setEditableContent] = useState(content);
  const [debouncedContent] = useDebounce(editableContent, 2000);

  const markAsDirty = useArtifactPortalStore((state) => state.markAsDirty);
  const clearDirtyState = useArtifactPortalStore((state) => state.clearDirtyState);
  const isDirty = artifactId ? !!useArtifactPortalStore((state) => state.dirtyArtifacts[artifactId]) : false;

  const isGenerating = useIsGenerating();
  const isInitialMount = useRef(true);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const [editorMounted, setEditorMounted] = useState<editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<MonacoNamespace | null>(null);
  const lineDecorationsRef = useRef<string[]>([]);
  const diffDecorationsRef = useRef<string[]>([]);

  // 获取 lineRange
  const lineRange = useArtifactPortalStore((state) => {
    if (!artifactId) return undefined;
    const tab = state.openTabs.find((t) => t.artifact.id === artifactId);
    return tab?.lineRange;
  });

  // 当外部 content 改变时（例如切换版本），重置内部状态
  useEffect(() => {
    setEditableContent(content);
  }, [content]);

  // 处理防抖保存
  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }

    if (artifactId) {
      if (debouncedContent !== content) {
        markAsDirty(artifactId, debouncedContent);
      } else {
        clearDirtyState(artifactId);
      }
    }
  }, [debouncedContent, artifactId, content, markAsDirty, clearDirtyState]);

  const applyLineRange = useCallback((rangeStr?: string) => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;

    if (!rangeStr) {
      // 清除高亮
      lineDecorationsRef.current = editor.deltaDecorations(lineDecorationsRef.current, []);
      return;
    }

    const parts = rangeStr.split('-');
    const startLine = parseInt(parts[0], 10);
    if (isNaN(startLine)) return;

    const endLine = parts.length > 1 && parts[1] ? parseInt(parts[1], 10) : startLine;
    const validEndLine = isNaN(endLine) ? startLine : endLine;

    // 滚动到目标行
    editor.revealLineInCenter(startLine);

    // 添加高亮
    lineDecorationsRef.current = editor.deltaDecorations(lineDecorationsRef.current, [
      {
        range: new monaco.Range(startLine, 1, validEndLine, 1),
        options: {
          isWholeLine: true,
          className: 'bg-primary/20',
          linesDecorationsClassName: 'bg-primary/50 w-1 ml-1',
        },
      },
    ]);
  }, []);

  const applyDiffDecorations = useCallback(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco || language !== 'diff') return;

    const model = editor.getModel();
    if (!model) return;

    const lines = model.getLinesContent();
    const newDecorations: editor.IModelDeltaDecoration[] = [];

    lines.forEach((line, index) => {
      const lineNumber = index + 1;
      if (line.startsWith('+') && !line.startsWith('+++')) {
        newDecorations.push({
          range: new monaco.Range(lineNumber, 1, lineNumber, 1),
          options: {
            isWholeLine: true,
            className: 'bg-green-500/20',
            marginClassName: 'bg-green-500/20',
          },
        });
      } else if (line.startsWith('-') && !line.startsWith('---')) {
        newDecorations.push({
          range: new monaco.Range(lineNumber, 1, lineNumber, 1),
          options: {
            isWholeLine: true,
            className: 'bg-red-500/20',
            marginClassName: 'bg-red-500/20',
          },
        });
      } else if (line.startsWith('@@')) {
        newDecorations.push({
          range: new monaco.Range(lineNumber, 1, lineNumber, 1),
          options: {
            isWholeLine: true,
            className: 'bg-blue-500/10 text-blue-500',
          },
        });
      }
    });

    diffDecorationsRef.current = editor.deltaDecorations(diffDecorationsRef.current, newDecorations);
  }, [language]);

  const handleEditorDidMount = useCallback(
    (editor: editor.IStandaloneCodeEditor, monaco: MonacoNamespace) => {
      editorRef.current = editor;
      monacoRef.current = monaco;
      setEditorMounted(editor);

      if (lineRange) {
        setTimeout(() => applyLineRange(lineRange), 100);
      }

      if (language === 'diff') {
        setTimeout(applyDiffDecorations, 100);
      }
    },
    [lineRange, applyLineRange, applyDiffDecorations, language],
  );

  // 监听内容变化以更新 diff 高亮
  useEffect(() => {
    if (language === 'diff') {
      applyDiffDecorations();
    }
  }, [editableContent, language, applyDiffDecorations]);

  // 监听 lineRange 变化
  useEffect(() => {
    applyLineRange(lineRange);
  }, [lineRange, applyLineRange]);

  // 映射语言到 Monaco 支持的语言
  const monacoLanguage = useMemo(() => {
    if (!language) return 'plaintext';
    const langMap: Record<string, string> = {
      js: 'javascript',
      ts: 'typescript',
      jsx: 'javascript',
      tsx: 'typescript',
      py: 'python',
      md: 'markdown',
      sh: 'shell',
      bash: 'shell',
      yml: 'yaml',
    };
    return langMap[language.toLowerCase()] || language.toLowerCase();
  }, [language]);

  return (
    <div className="h-full flex flex-col relative bg-background">
      {artifactId && (
        <div className="absolute top-2 right-6 z-10 text-xs text-muted-foreground bg-background/80 px-2 py-1 rounded backdrop-blur-sm border">
          {isDirty ? t('saving') : t('saved')}
        </div>
      )}
      <div className="flex-1 overflow-hidden relative">
        <Editor
          height="100%"
          language={monacoLanguage}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          value={editableContent}
          onChange={(val) => setEditableContent(val || '')}
          onMount={handleEditorDidMount}
          options={{
            minimap: { enabled: false },
            lineNumbers: 'on',
            glyphMargin: false,
            folding: true,
            wordWrap: 'on',
            readOnly: isGenerating || language === 'diff',
            padding: { top: 16, bottom: 16 },
            fontSize: 13,
            fontFamily: 'var(--font-mono)',
            scrollBeyondLastLine: false,
            renderLineHighlight: 'all',
            automaticLayout: true,
          }}
        />
        {editorMounted && (
          <SelectionToolbar editorInstance={editorMounted} artifactId={artifactId} language={language} />
        )}
      </div>
    </div>
  );
});

CodePreview.displayName = 'CodePreview';

export default CodePreview;
