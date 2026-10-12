// @orphan-ok Visual trust badge component rendering unendorsed external data quotes safely
'use client';

import React, { useState } from 'react';
import { ShieldCheck, Info, ChevronDown, ChevronUp } from 'lucide-react';

export interface QuotedAsDataProps {
  /** Domain classification label of the quoted text (e.g., '用户评价', '商品描述', '外部政策') */
  subject: string;
  /** Origin or provider of the external text */
  source?: string;
  /** The sanitized text content or child elements */
  children?: React.ReactNode;
  content?: string;
  /** Whether hardened data fencing has verified this quote */
  isVerified?: boolean;
  className?: string;
}

export const QuotedAsData: React.FC<QuotedAsDataProps> = ({
  subject,
  source,
  children,
  content,
  isVerified = true,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState(true);

  const displayContent = children ?? content ?? '';

  return (
    <section
      className={`my-3 w-full rounded-lg border border-border/60 bg-muted/30 dark:bg-muted/15 overflow-hidden transition-all duration-200 ${className}`}
      aria-label={`${subject} 原样呈现`}
    >
      {/* Top Header Badge */}
      <div className="flex items-center justify-between px-3.5 py-2 bg-muted/60 dark:bg-muted/30 border-b border-border/40 select-none">
        <div className="flex items-center gap-2 min-w-0">
          <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-500/10 text-blue-600 dark:text-blue-400">
            <ShieldCheck className="h-3.5 w-3.5" />
          </div>
          <span className="text-xs font-semibold text-foreground truncate">{subject}，原样呈现</span>
          {source && (
            <span className="text-[11px] text-muted-foreground/80 font-mono truncate max-w-[200px]">({source})</span>
          )}
          {isVerified && (
            <span className="inline-flex items-center rounded px-1.5 py-0.5 text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
              数据围栏已净化
            </span>
          )}
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground transition-colors p-1"
          aria-expanded={isExpanded}
        >
          <span>{isExpanded ? '收起' : '展开'}</span>
          {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>

      {/* Trust Disclaimer Notice */}
      <div className="flex items-center gap-1.5 px-3.5 py-1 text-[11px] text-muted-foreground/90 bg-muted/20 border-b border-border/20">
        <Info className="h-3 w-3 shrink-0 text-blue-500/70" />
        <span>此内容由外部提供，原样展示，未经官方模型背书</span>
      </div>

      {/* Quoted Content Body */}
      {isExpanded && (
        <div className="p-3.5 text-xs sm:text-sm text-foreground/90 leading-relaxed font-sans whitespace-pre-wrap break-words bg-background/50">
          {displayContent}
        </div>
      )}
    </section>
  );
};

export default QuotedAsData;
