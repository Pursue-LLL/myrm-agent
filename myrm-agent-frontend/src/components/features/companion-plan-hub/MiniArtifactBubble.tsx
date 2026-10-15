/**
 * MiniArtifactBubble.tsx
 * 完工成果气泡卡片：庆祝微动效、成果摘要与浏览器/源码/对话一键直达
 */

import React from 'react';
import {
  CheckCircle2,
  Code2,
  Globe,
  MessageSquare,
  Sparkles,
  X,
} from 'lucide-react';
import { useCompanionPlanHubStore } from './useCompanionPlanHubStore';

export interface MiniArtifactBubbleProps {
  className?: string;
  onOpenBrowser?: (url?: string) => void;
  onViewSource?: (path?: string) => void;
  onOpenConversation?: () => void;
  onClose?: () => void;
}

export const MiniArtifactBubble: React.FC<MiniArtifactBubbleProps> = ({
  className = '',
  onOpenBrowser,
  onViewSource,
  onOpenConversation,
  onClose,
}) => {
  const displayMode = useCompanionPlanHubStore((state) => state.displayMode);
  const completedArtifact = useCompanionPlanHubStore(
    (state) => state.completedArtifact
  );
  const setDisplayMode = useCompanionPlanHubStore(
    (state) => state.setDisplayMode
  );

  if (displayMode !== 'artifact_bubble' || completedArtifact === null) {
    return null;
  }

  const handleClose = (): void => {
    setDisplayMode('pet_only');
    if (onClose !== undefined) {
      onClose();
    }
  };

  const handleOpenBrowser = (): void => {
    if (onOpenBrowser !== undefined) {
      onOpenBrowser(completedArtifact.previewUrl);
    }
  };

  const handleViewSource = (): void => {
    if (onViewSource !== undefined) {
      onViewSource(completedArtifact.sourcePath);
    }
  };

  const handleOpenConversation = (): void => {
    if (onOpenConversation !== undefined) {
      onOpenConversation();
    }
  };

  return (
    <section
      data-testid="mini-artifact-bubble"
      aria-label="完工成果气泡卡片"
      className={`w-84 bg-slate-900/95 backdrop-blur-md border border-emerald-500/60 rounded-2xl shadow-2xl p-3.5 flex flex-col gap-3 text-slate-200 z-50 animate-in fade-in zoom-in-95 ${className}`}
    >
      {/* 头部庆祝标题与关闭 */}
      <div className="flex items-center justify-between border-b border-slate-800 pb-2">
        <div className="flex items-center gap-1.5">
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <h2 className="text-xs font-bold text-emerald-300">
            任务达成与自验证完毕
          </h2>
          <Sparkles className="w-3.5 h-3.5 text-amber-400 animate-pulse" />
        </div>

        <button
          type="button"
          data-testid="close-artifact-bubble-btn"
          aria-label="关闭成果气泡"
          onClick={handleClose}
          className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-slate-800"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* 成果卡片主要内容 */}
      <div className="flex flex-col gap-1 text-xs">
        <div className="font-semibold text-slate-100 line-clamp-1">
          {completedArtifact.title}
        </div>
        <p className="text-[11px] text-slate-400 leading-relaxed line-clamp-2">
          {completedArtifact.summaryText}
        </p>
      </div>

      {/* 完工快捷直达三大动作 */}
      <div className="grid grid-cols-3 gap-1.5 pt-1 border-t border-slate-800">
        <button
          type="button"
          data-testid="artifact-open-browser-btn"
          onClick={handleOpenBrowser}
          className="flex flex-col items-center justify-center p-2 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-emerald-500/50 hover:bg-emerald-950/20 text-slate-300 hover:text-emerald-300 transition-colors gap-1 text-[10px]"
        >
          <Globe className="w-4 h-4 text-emerald-400" />
          <span>浏览器打开</span>
        </button>

        <button
          type="button"
          data-testid="artifact-view-source-btn"
          onClick={handleViewSource}
          className="flex flex-col items-center justify-center p-2 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-blue-500/50 hover:bg-blue-950/20 text-slate-300 hover:text-blue-300 transition-colors gap-1 text-[10px]"
        >
          <Code2 className="w-4 h-4 text-blue-400" />
          <span>查看源码</span>
        </button>

        <button
          type="button"
          data-testid="artifact-open-conversation-btn"
          onClick={handleOpenConversation}
          className="flex flex-col items-center justify-center p-2 rounded-xl bg-slate-950/80 border border-slate-800 hover:border-purple-500/50 hover:bg-purple-950/20 text-slate-300 hover:text-purple-300 transition-colors gap-1 text-[10px]"
        >
          <MessageSquare className="w-4 h-4 text-purple-400" />
          <span>展开对话</span>
        </button>
      </div>
    </section>
  );
};
