'use client';

import React from 'react';

interface SkeletonLoaderProps {
  type?: string;
}

/** Skeleton 骨架屏加载状态 */
const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({ type }) => {
  if (type === 'image' || type === 'svg' || type === 'video') {
    return (
      <div className="h-full w-full flex items-center justify-center bg-muted/30 p-8">
        <div className="w-full max-w-md aspect-video rounded-lg bg-muted animate-pulse flex items-center justify-center">
          <div className="w-12 h-12 rounded-full bg-muted-foreground/10" />
        </div>
      </div>
    );
  }

  if (type === 'audio') {
    return (
      <div className="h-full w-full flex items-center justify-center bg-muted/30 p-8">
        <div className="flex flex-col items-center gap-6 w-full max-w-md animate-pulse">
          <div className="w-24 h-24 rounded-full bg-muted-foreground/10" />
          <div className="w-full h-10 bg-muted-foreground/10 rounded-full" />
        </div>
      </div>
    );
  }

  if (type === 'mermaid') {
    return (
      <div className="h-full w-full p-6 flex flex-col gap-4">
        <div className="flex-1 rounded-lg bg-muted animate-pulse flex items-center justify-center min-h-[200px]">
          <div className="flex flex-col items-center gap-3">
            <div className="w-24 h-8 rounded bg-muted-foreground/10" />
            <div className="flex gap-2">
              <div className="w-16 h-16 rounded-lg bg-muted-foreground/10" />
              <div className="w-16 h-16 rounded-lg bg-muted-foreground/10" />
              <div className="w-16 h-16 rounded-lg bg-muted-foreground/10" />
            </div>
            <div className="w-32 h-4 rounded bg-muted-foreground/10" />
          </div>
        </div>
      </div>
    );
  }

  if (type === 'pdf') {
    return (
      <div className="h-full w-full flex flex-col bg-muted/30">
        <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-muted animate-pulse" />
            <div className="w-20 h-4 rounded bg-muted animate-pulse" />
            <div className="w-8 h-8 rounded bg-muted animate-pulse" />
          </div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded bg-muted animate-pulse" />
            <div className="w-12 h-4 rounded bg-muted animate-pulse" />
            <div className="w-8 h-8 rounded bg-muted animate-pulse" />
          </div>
        </div>
        <div className="flex-1 flex justify-center items-center p-4">
          <div className="w-full max-w-lg aspect-[3/4] rounded-lg bg-muted animate-pulse shadow-lg" />
        </div>
      </div>
    );
  }

  // 默认：代码/文档类型的骨架屏
  return (
    <div className="h-full w-full p-4 space-y-3 bg-gray-50 dark:bg-gray-900">
      {Array.from({ length: 12 }).map((_, i) => (
        <div key={i} className="flex gap-3 animate-pulse">
          <div className="w-8 h-4 rounded bg-gray-200 dark:bg-gray-800" />
          <div
            className="h-4 rounded bg-gray-200 dark:bg-gray-800"
            style={{
              width: `${Math.random() * 40 + 30}%`,
              animationDelay: `${i * 50}ms`,
            }}
          />
        </div>
      ))}
    </div>
  );
};

export default SkeletonLoader;
