'use client';

import type { VisualApprovalContext } from '@/lib/approval/visualApprovalContext';

interface VisualApprovalHighlightProps {
  visualContext: VisualApprovalContext;
  maxHeight?: number;
  className?: string;
}

export default function VisualApprovalHighlight({
  visualContext,
  maxHeight = 300,
  className,
}: VisualApprovalHighlightProps) {
  const leftPercent = (visualContext.bbox.x / visualContext.viewportWidth) * 100;
  const topPercent = (visualContext.bbox.y / visualContext.viewportHeight) * 100;
  const widthPercent = (visualContext.bbox.width / visualContext.viewportWidth) * 100;
  const heightPercent = (visualContext.bbox.height / visualContext.viewportHeight) * 100;

  return (
    <div
      className={`relative overflow-hidden rounded-md border bg-black ${className ?? ''}`}
      style={{ maxHeight: `${maxHeight}px` }}
      data-testid="visual-approval-highlight"
    >
      <img
        src={`data:${visualContext.mimeType || 'image/jpeg'};base64,${visualContext.base64}`}
        alt="Approval target context"
        className="h-auto w-full object-contain opacity-80"
      />
      <div
        className="pointer-events-none absolute border-2 border-red-500 bg-red-500/20 shadow-[0_0_0_9999px_rgba(0,0,0,0.6)] transition-all animate-pulse"
        data-testid="visual-approval-bbox"
        style={{
          left: `${leftPercent}%`,
          top: `${topPercent}%`,
          width: `${widthPercent}%`,
          height: `${heightPercent}%`,
        }}
      />
    </div>
  );
}
