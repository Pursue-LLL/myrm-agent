'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: 前端国际化)
 * - lucide-react::Loader2 (POS: 加载图标组件)
 *
 * [OUTPUT]
 * - PublishLogsViewer: 工件发布实时日志视窗与动态进度呈现
 *
 * [POS]
 * 前端 Artifacts 特性组件层。承载工件部署过程中的 WebSocket 状态机日志展示与终端动效。
 */

import React from 'react';
import { Loader2 } from 'lucide-react';
import { useTranslations } from 'next-intl';

export interface PublishLogsViewerProps {
  logs: string[];
}

export const PublishLogsViewer: React.FC<PublishLogsViewerProps> = ({ logs }) => {
  const t = useTranslations('artifacts.publish');

  return (
    <div className="space-y-5 animate-in fade-in zoom-in-95 duration-300">
      <div className="flex flex-col items-center justify-center py-6 gap-4">
        <div className="relative">
          <div className="absolute inset-0 bg-primary/20 rounded-full blur-xl animate-pulse" />
          <Loader2 className="w-10 h-10 animate-spin text-primary relative z-10" />
        </div>
        <p className="text-sm font-medium text-muted-foreground animate-pulse">{t('publishing')}</p>
      </div>
      <div className="bg-muted/80 text-foreground/90 p-4 rounded-xl h-40 overflow-y-auto font-mono text-xs border border-border scrollbar-thin">
        {logs.map((log, i) => (
          <div key={i} className="mb-1 opacity-80 hover:opacity-100 transition-opacity">
            <span className="text-muted-foreground mr-2">[{new Date().toLocaleTimeString()}]</span>
            {log}
          </div>
        ))}
      </div>
    </div>
  );
};
