/**
 * BusinessMessageCard.tsx
 * 业务极简消息卡片：优雅排版商业计划/总结/澄清，并附带无损唤起底层工程追踪抽屉入口
 */

import React, { useMemo } from 'react';
import {
  Briefcase,
  CheckCircle2,
  ChevronRight,
  FileText,
  SearchCode,
  Sparkles,
} from 'lucide-react';
import type { TurnMessageItem } from './dualTrackTypes';
import {
  formatTraceSummaryBadge,
  summarizeEngineeringTrace,
} from './dualTrackEngine';
import { useDualTrackStore } from './useDualTrackStore';

export interface BusinessMessageCardProps {
  message: TurnMessageItem;
  className?: string;
  onOpenTrace?: () => void;
  onInspectArtifact?: (artifactId: string) => void;
}

export const BusinessMessageCard: React.FC<BusinessMessageCardProps> = ({
  message,
  className = '',
  onOpenTrace,
  onInspectArtifact,
}) => {
  const openTraceDrawer = useDualTrackStore((state) => state.openTraceDrawer);

  const traceSummary = useMemo(() => {
    return summarizeEngineeringTrace(message.traceDetails);
  }, [message.traceDetails]);

  const badgeText = useMemo(() => {
    return formatTraceSummaryBadge(traceSummary);
  }, [traceSummary]);

  const handleOpenTrace = (): void => {
    if (message.traceDetails !== undefined) {
      openTraceDrawer(message.traceDetails);
    }
    if (onOpenTrace !== undefined) {
      onOpenTrace();
    }
  };

  const hasTrace =
    message.traceDetails !== undefined &&
    (traceSummary.toolCount > 0 ||
      traceSummary.diffCount > 0 ||
      traceSummary.logLineCount > 0);

  const cardData = message.businessCardData;

  return (
    <article
      data-testid={`business-message-card-${message.id}`}
      aria-label="业务对话卡片"
      className={`relative flex flex-col bg-slate-900 border border-slate-800 rounded-2xl p-4 shadow-md text-slate-200 gap-3 ${className}`}
    >
      {/* 头部：角色标识与底层工程抽屉唤起按钮 */}
      <div className="flex items-center justify-between border-b border-slate-800/80 pb-2.5">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-lg bg-blue-950/60 text-blue-400 border border-blue-800/50">
            <Briefcase className="w-3.5 h-3.5" />
          </div>
          <span className="text-xs font-semibold text-slate-100">
            {cardData?.title ?? '业务对齐回复'}
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
            极简业务视图
          </span>
        </div>

        {/* 右上角底层工程追踪入口按钮 */}
        {hasTrace && (
          <button
            type="button"
            data-testid="inspect-engineering-trace-btn"
            aria-label="查看底层代码与执行细节"
            onClick={handleOpenTrace}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-medium bg-slate-950/70 hover:bg-slate-800 border border-slate-700/80 text-blue-400 hover:text-blue-300 transition-colors shadow-sm"
            title={`点击查看底层代码变更与命令日志: ${badgeText}`}
          >
            <SearchCode className="w-3.5 h-3.5" />
            <span className="hidden sm:inline">底层工程细节</span>
            <span className="text-[10px] text-slate-500 font-mono">
              ({traceSummary.toolCount} 工具 / {traceSummary.diffCount} Diff)
            </span>
            <ChevronRight className="w-3 h-3 text-slate-500" />
          </button>
        )}
      </div>

      {/* 核心业务总结/叙事内容 */}
      <div className="text-xs text-slate-300 leading-relaxed space-y-2">
        {cardData?.summary !== undefined ? (
          <p data-testid="business-summary-text">{cardData.summary}</p>
        ) : (
          <p>{message.content}</p>
        )}
      </div>

      {/* 结构化业务步骤列表（若有） */}
      {cardData?.planSteps !== undefined && cardData.planSteps.length > 0 && (
        <div
          data-testid="business-plan-steps-deck"
          className="bg-slate-950/50 rounded-xl p-3 border border-slate-800/80 flex flex-col gap-1.5"
        >
          <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-amber-400" />
            <span>落地业务执行路径:</span>
          </div>
          <ul className="flex flex-col gap-1 pl-1">
            {cardData.planSteps.map((step, idx) => (
              <li
                key={idx}
                className="flex items-center gap-1.5 text-xs text-slate-200"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
                <span>{step}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 直出工件快捷检视条 */}
      {cardData?.artifactId !== undefined && (
        <div className="flex items-center justify-between p-2 rounded-xl bg-blue-950/20 border border-blue-900/40 text-xs">
          <div className="flex items-center gap-1.5 text-blue-300">
            <FileText className="w-3.5 h-3.5" />
            <span>关联生成工件: {cardData.artifactId}</span>
          </div>
          {onInspectArtifact !== undefined && (
            <button
              type="button"
              data-testid="inspect-artifact-btn"
              onClick={() => {
                const id = cardData.artifactId;
                if (id !== undefined) {
                  onInspectArtifact(id);
                }
              }}
              className="text-blue-400 hover:text-blue-200 underline font-medium"
            >
              直接打开交互工件
            </button>
          )}
        </div>
      )}
    </article>
  );
};
