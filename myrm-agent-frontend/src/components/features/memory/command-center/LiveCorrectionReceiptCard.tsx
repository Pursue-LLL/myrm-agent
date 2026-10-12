/**
 * [INPUT]
 * @/services/memory::CorrectionAckReceiptDTO
 * Lucide icons (CheckCircle, Clock, FileCheck, MessageSquareQuote, ShieldCheck)
 *
 * [OUTPUT]
 * Component: LiveCorrectionReceiptCard
 *
 * [POS]
 * Natural language acknowledgement receipt & audit trail card for Item 128 Live Correction Studio.
 * Strictly typed, zero any, a11y compliant with visible focus rings. Single file < 200 lines.
 */

'use client';

import React from 'react';
import { CheckCircle, Clock, FileCheck, MessageSquareQuote, ShieldCheck } from 'lucide-react';
import type { CorrectionAckReceiptDTO } from '@/services/memory';

interface LiveCorrectionReceiptCardProps {
  receipt: CorrectionAckReceiptDTO;
}

export const LiveCorrectionReceiptCard: React.FC<LiveCorrectionReceiptCardProps> = ({
  receipt,
}) => {
  const auditEntries = receipt.mutated_record?.audit_trail
    ? Object.entries(receipt.mutated_record.audit_trail)
    : [];

  return (
    <section
      aria-label="即时重校执行回执与自然语言反馈"
      className="space-y-3 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <FileCheck className="h-4 w-4 text-emerald-500" aria-hidden="true" />
          <h3 className="text-sm font-semibold text-foreground">
            即时重校执行回执 (Live Correction Receipt)
          </h3>
        </div>
        <div className="flex items-center gap-3 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
            <CheckCircle className="h-3.5 w-3.5" aria-hidden="true" />
            <span>执行成功</span>
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3.5 w-3.5" aria-hidden="true" />
            <span>{receipt.processing_ms} ms</span>
          </span>
        </div>
      </div>

      {/* Natural Language Acknowledgement Speech Bubble */}
      <div className="rounded-lg border border-border/80 bg-background/80 p-3.5 shadow-xs">
        <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-primary">
          <MessageSquareQuote className="h-4 w-4" aria-hidden="true" />
          <span>对话助手即时应答确认 (Natural Language Acknowledgement):</span>
        </div>
        <p className="text-sm font-medium leading-relaxed text-foreground">
          &ldquo;{receipt.ack_message}&rdquo;
        </p>
      </div>

      {/* Audit Trail Details */}
      {auditEntries.length > 0 && (
        <div className="rounded-lg border border-border/60 bg-muted/30 p-2.5 text-xs">
          <div className="mb-1.5 flex items-center gap-1.5 font-medium text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
            <span>不可篡改审计追踪 (Immutable Audit Trail):</span>
          </div>
          <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2 md:grid-cols-3">
            {auditEntries.map(([key, value]) => (
              <div
                key={key}
                className="flex items-center justify-between rounded border border-border/40 bg-background/60 px-2 py-1 font-mono text-[11px]"
              >
                <span className="text-muted-foreground">{key}:</span>
                <span className="font-semibold text-foreground">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </section>
  );
};
