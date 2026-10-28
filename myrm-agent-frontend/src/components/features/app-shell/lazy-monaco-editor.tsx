'use client';

/**
 * [INPUT]
 * - @monaco-editor/react, monaco-editor (POS: 编辑器与随包的 Monaco 本体)
 * - next-themes::useTheme (POS: 应用明暗主题)
 *
 * [OUTPUT]
 * - LazyMonacoEditor / LazyMonacoDiffEditor: 懒加载的 Monaco 编辑器 / 对比编辑器，主题由本文件统一决定
 *
 * [POS]
 * 全站唯一的 Monaco 入口。Monaco 的主题是整页共享的：任何一个编辑器挂载时传入的主题都会改写
 * 同一页面上所有编辑器，所以调用方不能各自传 `theme`。加载时先把随包的 Monaco 登记给
 * loader，避免 `@monaco-editor/react` 回退到 CDN。
 */

import dynamic from 'next/dynamic';
import { useTheme } from 'next-themes';
import { Loader2 } from 'lucide-react';
import type { EditorProps, DiffEditorProps } from '@monaco-editor/react';

export type LazyMonacoEditorProps = Omit<EditorProps, 'theme'>;
export type LazyMonacoDiffEditorProps = Omit<DiffEditorProps, 'theme'>;

type MonacoThemeName = 'vs' | 'vs-dark';

const Loading = () => (
  <div className="flex items-center justify-center h-full w-full min-h-[400px] bg-muted/30">
    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
  </div>
);

const MonacoEditor = dynamic<EditorProps>(
  () =>
    Promise.all([import('@monaco-editor/react'), import('monaco-editor')]).then(([reactMod, monacoMod]) => {
      reactMod.loader.config({ monaco: monacoMod });
      return reactMod.Editor;
    }),
  {
    ssr: false,
    loading: Loading,
  },
);

const MonacoDiffEditor = dynamic<DiffEditorProps>(
  () =>
    Promise.all([import('@monaco-editor/react'), import('monaco-editor')]).then(([reactMod, monacoMod]) => {
      reactMod.loader.config({ monaco: monacoMod });
      return reactMod.DiffEditor;
    }),
  {
    ssr: false,
    loading: Loading,
  },
);

function useMonacoTheme(): MonacoThemeName {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === 'dark' ? 'vs-dark' : 'vs';
}

export function LazyMonacoEditor(props: LazyMonacoEditorProps) {
  const theme = useMonacoTheme();
  return <MonacoEditor {...props} theme={theme} />;
}

export function LazyMonacoDiffEditor(props: LazyMonacoDiffEditorProps) {
  const theme = useMonacoTheme();
  return <MonacoDiffEditor {...props} theme={theme} />;
}
