/**
 * [INPUT]
 * - react (POS: UI Framework)
 * - lucide-react (POS: Consistent vector icons)
 * - @/components/features/chat-window/final-card/finalCardTypes
 * - @/components/features/chat-window/final-card/finalCardEngine
 * - @/components/features/chat-window/final-card/useFinalCardStore
 *
 * [OUTPUT]
 * - TerminalFreeFinalCard (POS: High-fidelity structured final presentation card component)
 *
 * [POS]
 * Primary presentation UI for Item 192 (P0).
 * Replaces raw terminal output with structured achievements, key decisions,
 * generated artifacts, and actionable next steps.
 */

import React from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  HelpCircle,
  Clock,
  Cpu,
  FileCode,
  FileText,
  FileDiff,
  File,
  Terminal,
  ExternalLink,
  ChevronRight,
} from 'lucide-react';
import type {
  FinalCardStatus,
  FinalCardArtifact,
  FinalCardActionOption,
  FinalCardPresentationContract,
} from './finalCardTypes';
import {
  formatDurationText,
  formatSizeBytes,
} from './finalCardEngine';
import { useFinalCardStore } from './useFinalCardStore';

export interface TerminalFreeFinalCardProps {
  readonly contract: FinalCardPresentationContract;
  readonly onActionClick?: (action: FinalCardActionOption) => void;
  readonly onArtifactClick?: (artifact: FinalCardArtifact) => void;
  readonly onViewTranscript?: () => void;
  readonly className?: string;
}

function getStatusBadge(status: FinalCardStatus) {
  switch (status) {
    case 'completed': {
      return {
        label: '已完成',
        icon: <CheckCircle2 className="w-4 h-4 text-emerald-500" />,
        bgClass: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
      };
    }
    case 'requires_action': {
      return {
        label: '待确认',
        icon: <HelpCircle className="w-4 h-4 text-amber-500" />,
        bgClass: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
      };
    }
    case 'partial_success': {
      return {
        label: '部分完成',
        icon: <AlertTriangle className="w-4 h-4 text-yellow-500" />,
        bgClass: 'bg-yellow-500/10 text-yellow-600 dark:text-yellow-400 border-yellow-500/20',
      };
    }
    case 'failed': {
      return {
        label: '失败',
        icon: <XCircle className="w-4 h-4 text-rose-500" />,
        bgClass: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
      };
    }
  }
}

function getArtifactIcon(type: FinalCardArtifact['type']) {
  switch (type) {
    case 'code': {
      return <FileCode className="w-3.5 h-3.5 text-blue-500" />;
    }
    case 'document': {
      return <FileText className="w-3.5 h-3.5 text-purple-500" />;
    }
    case 'diff': {
      return <FileDiff className="w-3.5 h-3.5 text-orange-500" />;
    }
    case 'binary': {
      return <File className="w-3.5 h-3.5 text-slate-500" />;
    }
  }
}

export const TerminalFreeFinalCard: React.FC<TerminalFreeFinalCardProps> = ({
  contract,
  onActionClick,
  onArtifactClick,
  onViewTranscript,
  className = '',
}) => {
  const openTranscriptModal = useFinalCardStore((state) => state.openTranscriptModal);
  const statusBadge = getStatusBadge(contract.status);

  const handleOpenTranscript = () => {
    if (onViewTranscript) {
      onViewTranscript();
    } else {
      openTranscriptModal(contract.id);
    }
  };

  return (
    <div
      data-testid={`final-card-${contract.id}`}
      className={`rounded-xl border border-border/80 bg-card p-5 shadow-sm transition-all hover:shadow-md ${className}`}
    >
      {/* 头部：标题与状态徽章 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border/50 pb-3">
        <div className="flex items-center gap-2">
          <div
            className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusBadge.bgClass}`}
          >
            {statusBadge.icon}
            <span>{statusBadge.label}</span>
          </div>
          <h3 className="text-base font-semibold text-foreground tracking-tight">
            {contract.title}
          </h3>
        </div>

        {/* 性能与消耗计量器 */}
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <div className="flex items-center gap-1" title="任务总耗时">
            <Clock className="w-3.5 h-3.5 text-muted-foreground/70" />
            <span>{formatDurationText(contract.executionDurationMs)}</span>
          </div>
          {contract.tokensUsed ? (
            <div
              className="flex items-center gap-1"
              title={`Tokens: ${contract.tokensUsed.prompt} prompt / ${contract.tokensUsed.completion} completion`}
            >
              <Cpu className="w-3.5 h-3.5 text-muted-foreground/70" />
              <span>{contract.tokensUsed.total.toLocaleString()} tokens</span>
            </div>
          ) : null}
        </div>
      </div>

      {/* 核心结论与摘要 */}
      <div className="mt-3 text-sm text-foreground/90 leading-relaxed">
        {contract.summary}
      </div>

      {/* 关键决策点 */}
      {contract.keyDecisions.length > 0 ? (
        <div className="mt-4 rounded-lg bg-muted/40 p-3">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            关键架构决策
          </h4>
          <ul className="space-y-1.5 text-xs text-foreground/80">
            {contract.keyDecisions.map((decision, index) => (
              <li key={`decision-${index}`} className="flex items-start gap-2">
                <ChevronRight className="w-3.5 h-3.5 text-primary shrink-0 mt-0.5" />
                <span>{decision}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 产出物工件网格 */}
      {contract.artifacts.length > 0 ? (
        <div className="mt-4">
          <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground mb-2">
            生成工件 ({contract.artifacts.length})
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {contract.artifacts.map((art) => (
              <button
                key={art.id}
                type="button"
                onClick={() => {
                  if (onArtifactClick) {
                    onArtifactClick(art);
                  }
                }}
                className="flex items-center justify-between rounded-md border border-border/60 bg-muted/20 px-3 py-2 text-left text-xs transition-colors hover:bg-accent hover:border-accent-foreground/20"
              >
                <div className="flex items-center gap-2 truncate">
                  {getArtifactIcon(art.type)}
                  <span className="font-medium text-foreground truncate">{art.name}</span>
                </div>
                {art.sizeBytes ? (
                  <span className="ml-2 text-muted-foreground text-[10px] shrink-0">
                    {formatSizeBytes(art.sizeBytes)}
                  </span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {/* 下一步交互动作选项 */}
      {contract.actionOptions.length > 0 ? (
        <div className="mt-4 flex flex-wrap items-center gap-2 pt-2 border-t border-border/40">
          {contract.actionOptions.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => {
                if (onActionClick) {
                  onActionClick(opt);
                }
              }}
              className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all ${
                opt.isPrimary
                  ? 'bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm'
                  : 'bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border/50'
              }`}
            >
              <span>{opt.label}</span>
              <ChevronRight className="w-3 h-3 opacity-70" />
            </button>
          ))}
        </div>
      ) : null}

      {/* 底部查看 Transcript 入口 */}
      <div className="mt-4 flex items-center justify-between pt-3 text-xs border-t border-border/30 text-muted-foreground">
        <button
          type="button"
          onClick={handleOpenTranscript}
          className="inline-flex items-center gap-1.5 text-primary hover:underline font-medium"
        >
          <Terminal className="w-3.5 h-3.5" />
          <span>
            调阅执行轨迹
            {contract.rawLogLinesCount > 0 ? ` (${contract.rawLogLinesCount} 行日志)` : ''}
          </span>
        </button>

        <a
          href={contract.transcriptUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 hover:text-foreground transition-colors"
        >
          <span>完整日志链接</span>
          <ExternalLink className="w-3 h-3" />
        </a>
      </div>
    </div>
  );
};
