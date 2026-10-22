import React, { useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Lock,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  Tag,
} from 'lucide-react';
import { EnrichedPresentationResult } from './uiEnrichmentTypes';

interface AntiTamperEnrichedCardProps {
  result: EnrichedPresentationResult;
  className?: string;
}

export const AntiTamperEnrichedCard: React.FC<AntiTamperEnrichedCardProps> = ({
  result,
  className = '',
}) => {
  const [showAudit, setShowAudit] = useState(false);
  const { items, auditLog } = result;

  const hasAuditNotes =
    auditLog.droppedUnknownIds.length > 0 ||
    auditLog.currencyFixedCount > 0 ||
    auditLog.temporalFixedCount > 0;

  return (
    <div
      data-testid={`anti-tamper-card-${result.presentationId}`}
      className={`my-3 w-full max-w-xl rounded-xl border border-emerald-500/30 bg-background/95 p-4 text-xs shadow-md backdrop-blur-md dark:bg-muted/30 ${className}`}
    >
      {/* 头部标题与权威事实 Join 微标 */}
      <div className="flex items-start justify-between gap-2 border-b border-border/40 pb-3">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="h-4 w-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-semibold text-foreground text-sm">
                权威事实防篡改卡片
              </span>
              <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                服务端事实全量 Join · 零模型伪造风险
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-muted-foreground">
              定价、标题与库存 100% 取自系统权威事实库，模型仅携带主观判定
            </p>
          </div>
        </div>

        <span className="font-mono text-[10px] text-muted-foreground">
          {items.length} 权威项
        </span>
      </div>

      {/* 结构化权威事实条目列表 */}
      <div className="mt-3 space-y-2.5">
        {items.map((item) => {
          const currencySymbol = item.officialCurrency === 'USD' ? '$' : '¥';

          return (
            <div
              key={item.id}
              className="rounded-lg border border-border/60 bg-background/80 p-3 shadow-2xs transition-all hover:border-emerald-500/40"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-emerald-500/10 font-mono text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                    {item.rank}
                  </span>
                  <div>
                    <span className="font-medium text-foreground text-xs">
                      {item.officialTitle}
                    </span>
                    <span className="ml-2 font-mono text-[10px] text-muted-foreground">
                      ID: {item.id}
                    </span>
                  </div>
                </div>

                {/* 真实官方标价与安全锁 */}
                <div className="flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                  <Lock className="h-3 w-3" />
                  <span>
                    {currencySymbol}
                    {item.officialPrice}
                  </span>
                </div>
              </div>

              {/* 模型推荐短评与高亮标签 (经过跨模态自洽清洗) */}
              <div className="mt-2 text-[11px]">
                {item.sanitizedNote && (
                  <p className="text-muted-foreground">
                    <span className="font-medium text-foreground">推荐评述: </span>
                    {item.sanitizedNote}
                  </p>
                )}
                {item.comparisonHighlight && (
                  <div className="mt-1 flex items-center gap-1 text-[10px] text-amber-600 dark:text-amber-400">
                    <Sparkles className="h-3 w-3" />
                    <span>{item.comparisonHighlight}</span>
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 审计日志折叠面板 */}
      {hasAuditNotes && (
        <div className="mt-3 border-t border-border/30 pt-2 text-[11px]">
          <button
            type="button"
            onClick={() => {
              setShowAudit(!showAudit);
            }}
            className="flex w-full items-center justify-between text-muted-foreground hover:text-foreground"
          >
            <div className="flex items-center gap-1.5 text-amber-600 dark:text-amber-400">
              <ShieldAlert className="h-3.5 w-3.5" />
              <span>
                防篡改门禁已执行安全清洗 ({auditLog.auditNotes.length} 项记录)
              </span>
            </div>
            {showAudit ? (
              <ChevronUp className="h-3.5 w-3.5" />
            ) : (
              <ChevronDown className="h-3.5 w-3.5" />
            )}
          </button>

          {showAudit && (
            <div className="mt-2 space-y-1 rounded-lg border border-amber-500/30 bg-amber-500/5 p-2 font-mono text-[10px] text-amber-700 dark:text-amber-300">
              {auditLog.auditNotes.map((note, idx) => (
                <div key={idx} className="flex items-start gap-1">
                  <span>•</span>
                  <span>{note}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
