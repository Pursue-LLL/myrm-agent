import React from 'react';
import {
  Check,
  Clock,
  Code2,
  Database,
  ExternalLink,
  FileText,
  Film,
  Sparkles,
  X,
} from 'lucide-react';
import { formatDuration } from './fullDuplexBridgeEngine';
import { ArtifactType, ReanchoredResultCard } from './fullDuplexBridgeTypes';
import { useFullDuplexBridgeStore } from './useFullDuplexBridgeStore';

interface ContextualResultReanchoringCardProps {
  card: ReanchoredResultCard;
  onAdopt?: (card: ReanchoredResultCard) => void;
  onViewArtifact?: (card: ReanchoredResultCard) => void;
  className?: string;
}

function renderArtifactTypeIcon(type: ArtifactType) {
  if (type === 'code') {
    return <Code2 className="h-3.5 w-3.5 text-blue-500" />;
  }
  if (type === 'video') {
    return <Film className="h-3.5 w-3.5 text-purple-500" />;
  }
  if (type === 'data') {
    return <Database className="h-3.5 w-3.5 text-amber-500" />;
  }
  return <FileText className="h-3.5 w-3.5 text-emerald-500" />;
}

export const ContextualResultReanchoringCard: React.FC<
  ContextualResultReanchoringCardProps
> = ({ card, onAdopt, onViewArtifact, className = '' }) => {
  const markResultAdopted = useFullDuplexBridgeStore(
    (state) => state.markResultAdopted,
  );
  const dismissResult = useFullDuplexBridgeStore(
    (state) => state.dismissResult,
  );

  const handleAdoptClick = () => {
    markResultAdopted(card.id);
    if (onAdopt) {
      onAdopt(card);
    }
  };

  const handleViewClick = () => {
    if (onViewArtifact) {
      onViewArtifact(card);
    }
  };

  return (
    <div
      data-testid={`reanchored-result-${card.id}`}
      className={`my-3 overflow-hidden rounded-xl border border-primary/20 bg-primary/5 p-3.5 shadow-sm backdrop-blur-md transition-all dark:bg-primary/10 ${className}`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-background shadow-xs">
            {renderArtifactTypeIcon(card.artifact.type)}
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                后台成果已就绪
              </span>
              <span className="flex items-center gap-1 text-[11px] text-muted-foreground">
                <Clock className="h-3 w-3" />
                耗时 {formatDuration(card.elapsedSec)}
              </span>
            </div>
            <h4 className="mt-0.5 text-xs font-semibold text-foreground">
              {card.title}
            </h4>
          </div>
        </div>

        <button
          type="button"
          onClick={() => {
            dismissResult(card.id);
          }}
          className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
          aria-label="关闭成果通知卡片"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      {/* 摘要与预览片段 */}
      <div className="mt-2 text-xs leading-relaxed text-muted-foreground">
        <p>{card.artifact.summary}</p>
        {card.artifact.previewSnippet && (
          <div className="mt-2 rounded bg-background/80 p-2 font-mono text-[11px] text-foreground/80 border border-border/40">
            {card.artifact.previewSnippet}
          </div>
        )}
      </div>

      {/* 操作按钮组 */}
      <div className="mt-3 flex items-center justify-between gap-2 pt-2 border-t border-border/30">
        <span className="text-[11px] text-muted-foreground">
          {card.artifact.title}
        </span>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleViewClick}
            className="flex items-center gap-1 rounded-md border border-border/60 bg-background px-2.5 py-1 text-xs font-medium text-foreground transition-colors hover:bg-muted"
          >
            <span>预览工件</span>
            <ExternalLink className="h-3 w-3 text-muted-foreground" />
          </button>

          <button
            type="button"
            onClick={handleAdoptClick}
            disabled={card.isAdopted}
            className={`flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors ${
              card.isAdopted
                ? 'bg-muted text-muted-foreground cursor-default'
                : 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-xs'
            }`}
          >
            {card.isAdopted ? (
              <>
                <Check className="h-3.5 w-3.5" />
                <span>已采纳至会话</span>
              </>
            ) : (
              <>
                <Sparkles className="h-3.5 w-3.5" />
                <span>采纳并继续讨论</span>
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
};
