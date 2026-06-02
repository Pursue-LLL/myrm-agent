'use client';

import React, { memo, Suspense } from 'react';
import MermaidChart from '../../markdown-render-tools/MermaidChart';

/** 简单加载状态 */
const LoadingState: React.FC = () => (
  <div className="h-full flex items-center justify-center">
    <div className="animate-spin w-8 h-8 border-2 border-muted-foreground/30 border-t-primary rounded-full" />
  </div>
);

/** Mermaid 图表预览组件 */
const MermaidPreview: React.FC<{ content: string }> = memo(({ content }) => {
  return (
    <div className="h-full w-full overflow-auto p-4">
      <Suspense fallback={<LoadingState />}>
        <MermaidChart chart={content} />
      </Suspense>
    </div>
  );
});
MermaidPreview.displayName = 'MermaidPreview';

export default MermaidPreview;
