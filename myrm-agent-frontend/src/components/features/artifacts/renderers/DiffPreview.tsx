'use client';

/**
 * [INPUT]
 * `ArtifactVersion[]`（版本列表，含 `.content`）；`viewingVersionIndex`（当前查看版本）。
 * [OUTPUT] DiffPreview: Monaco DiffEditor 渲染版本间差异，支持 inline/side-by-side 切换。
 * [POS] `artifacts/renderers/` 渲染器之一；由 `ArtifactRenderer` 在 `ArtifactDisplayMode.Diff` 时挂载。
 */

import React, { useMemo, useState } from 'react';
import { useTheme } from 'next-themes';
import { useTranslations } from 'next-intl';
import { cn } from '@/lib/utils/classnameUtils';
import { LazyMonacoDiffEditor } from '@/components/features/app-shell/lazy-monaco-editor';
import type { ArtifactVersion } from '@/store/chat/types';
import { MOBILE_BREAKPOINT } from '@/lib/constants/artifact';

interface DiffPreviewProps {
  /** 当前（最新或选中）版本的内容 */
  currentContent: string;
  /** 所有版本列表 */
  versions: ArtifactVersion[];
  /** 当前查看的版本索引（-1 表示最新） */
  viewingVersionIndex: number;
  /** 文件语言（用于语法高亮） */
  language?: string;
}

/**
 * 版本间 Diff 渲染器。
 * 使用 Monaco DiffEditor 显示当前版本与上一版本的差异。
 * 支持 inline（单栏）和 side-by-side（双栏）两种展示模式。
 */
const DiffPreview: React.FC<DiffPreviewProps> = ({
  currentContent,
  versions,
  viewingVersionIndex,
  language,
}) => {
  const { resolvedTheme } = useTheme();
  const t = useTranslations('artifacts');
  const [renderSideBySide, setRenderSideBySide] = useState(
    () => typeof window !== 'undefined' && window.innerWidth >= MOBILE_BREAKPOINT,
  );

  const { original, modified, originalVersion, modifiedVersion } = useMemo(() => {
    const effectiveIndex = viewingVersionIndex === -1 ? versions.length - 1 : viewingVersionIndex;
    const prevIndex = effectiveIndex - 1;

    const modifiedContent =
      viewingVersionIndex === -1
        ? currentContent
        : (versions[effectiveIndex]?.content ?? currentContent);

    const originalContent = prevIndex >= 0 ? (versions[prevIndex]?.content ?? '') : '';

    return {
      original: originalContent,
      modified: modifiedContent,
      originalVersion: prevIndex >= 0 ? versions[prevIndex]?.versionNumber : undefined,
      modifiedVersion: versions[effectiveIndex]?.versionNumber,
    };
  }, [versions, viewingVersionIndex, currentContent]);

  if (versions.length < 2) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        {t('diff.noVersions')}
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/30 shrink-0">
        {originalVersion != null && modifiedVersion != null && (
          <span className="text-xs text-muted-foreground">
            V{originalVersion} → V{modifiedVersion}
          </span>
        )}
        <div className="flex items-center bg-muted rounded-md p-0.5">
          <button
            onClick={() => setRenderSideBySide(false)}
            className={cn(
              'px-2 py-0.5 rounded text-xs font-medium transition-colors',
              !renderSideBySide
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t('diff.inline')}
          </button>
          <button
            onClick={() => setRenderSideBySide(true)}
            className={cn(
              'px-2 py-0.5 rounded text-xs font-medium transition-colors',
              renderSideBySide
                ? 'bg-background text-foreground shadow-sm'
                : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t('diff.sideBySide')}
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-hidden">
        <LazyMonacoDiffEditor
          original={original}
          modified={modified}
          language={language ?? 'plaintext'}
          theme={resolvedTheme === 'dark' ? 'vs-dark' : 'light'}
          options={{
            readOnly: true,
            renderSideBySide,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            fontSize: 13,
            lineNumbers: 'on',
            wordWrap: 'on',
            automaticLayout: true,
          }}
        />
      </div>
    </div>
  );
};

export default DiffPreview;
