'use client';

import dynamic from 'next/dynamic';
import { Loader2 } from 'lucide-react';
import type { EditorProps, DiffEditorProps } from '@monaco-editor/react';

const Loading = () => (
  <div className="flex items-center justify-center h-full w-full min-h-[400px] bg-muted/30">
    <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
  </div>
);

export const LazyMonacoEditor = dynamic<EditorProps>(() => import('@monaco-editor/react').then((mod) => mod.Editor), {
  ssr: false,
  loading: Loading,
});

export const LazyMonacoDiffEditor = dynamic<DiffEditorProps>(
  () => import('@monaco-editor/react').then((mod) => mod.DiffEditor),
  {
    ssr: false,
    loading: Loading,
  },
);
