/**
 * [INPUT] ImmutableOperationReceipt, optional compact flag, onCopySha
 * [OUTPUT] OperationReceiptBadge component rendering cryptographically signed audit receipt
 * [POS] task-action-preview/OperationReceiptBadge.tsx
 */

'use client';

import React, { useState, useCallback } from 'react';
import {
  ShieldCheck,
  Hash,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Clock,
  User,
  AlertCircle,
  FileCheck2,
} from 'lucide-react';
import type { ImmutableOperationReceipt } from './taskActionPreviewTypes';

export interface OperationReceiptBadgeProps {
  receipt: ImmutableOperationReceipt;
  defaultExpanded?: boolean;
  className?: string;
}

export const OperationReceiptBadge: React.FC<OperationReceiptBadgeProps> = ({
  receipt,
  defaultExpanded = false,
  className = '',
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(defaultExpanded);
  const [copied, setCopied] = useState<boolean>(false);

  const handleCopySha = useCallback(
    (e: React.MouseEvent<HTMLButtonElement>) => {
      e.stopPropagation();
      if (typeof navigator !== 'undefined' && navigator.clipboard) {
        navigator.clipboard.writeText(receipt.targetSha);
        setCopied(true);
        setTimeout(() => {
          setCopied(false);
        }, 2000);
      }
    },
    [receipt.targetSha],
  );

  const formattedTime = new Date(receipt.timestamp).toLocaleString();
  const shortSha = receipt.targetSha.slice(0, 8);
  const isSuccess = receipt.status === 'success';

  return (
    <div
      data-testid="operation-receipt-card"
      className={`rounded-lg border bg-card text-card-foreground shadow-sm transition-all text-xs overflow-hidden ${
        isSuccess ? 'border-border/70' : 'border-destructive/40'
      } ${className}`}
    >
      {/* Clickable Header Bar */}
      <button
        type="button"
        onClick={() => {
          setIsExpanded((prev) => !prev);
        }}
        className="w-full flex items-center justify-between px-3 py-2 bg-muted/30 hover:bg-muted/50 transition-colors text-left"
        aria-expanded={isExpanded}
        aria-label="操作回执审计摘要"
      >
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold ${
              isSuccess
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20'
                : 'bg-destructive/10 text-destructive border border-destructive/20'
            }`}
          >
            {isSuccess ? (
              <ShieldCheck className="h-3 w-3" />
            ) : (
              <AlertCircle className="h-3 w-3" />
            )}
            {receipt.statusCode} {receipt.status.toUpperCase()}
          </span>

          <span className="font-mono text-muted-foreground text-[11px]">
            ID: {receipt.receiptId}
          </span>

          <span className="inline-flex items-center gap-1 font-mono text-muted-foreground text-[11px] bg-muted/60 px-1.5 py-0.5 rounded">
            <Hash className="h-2.5 w-2.5" />
            {shortSha}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[11px] text-muted-foreground hidden sm:inline">
            不可篡改操作回执
          </span>
          {isExpanded ? (
            <ChevronUp className="h-3.5 w-3.5 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          )}
        </div>
      </button>

      {/* Expanded Detailed Audit Body */}
      {isExpanded && (
        <div className="px-3 py-2.5 space-y-2 border-t border-border/50 bg-background/50">
          <p className="text-foreground leading-relaxed">{receipt.summary}</p>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-[11px] text-muted-foreground pt-1">
            <div className="flex items-center gap-1.5">
              <User className="h-3 w-3 text-primary/70 shrink-0" />
              <span>操作人：</span>
              <span className="font-medium text-foreground">{receipt.operator}</span>
            </div>

            <div className="flex items-center gap-1.5">
              <Clock className="h-3 w-3 text-primary/70 shrink-0" />
              <span>时间戳：</span>
              <span className="font-mono text-foreground">{formattedTime}</span>
            </div>
          </div>

          {/* Cryptographic SHA & Signature Badge */}
          <div className="rounded border bg-muted/20 p-2 text-[11px] font-mono space-y-1">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground flex items-center gap-1">
                <FileCheck2 className="h-3 w-3 text-emerald-500" />
                Target SHA-256 Signature:
              </span>
              <button
                type="button"
                onClick={handleCopySha}
                title="复制 SHA 签名"
                aria-label="复制 SHA 签名"
                className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded hover:bg-muted text-muted-foreground hover:text-foreground transition-colors"
              >
                {copied ? (
                  <Check className="h-2.5 w-2.5 text-emerald-500" />
                ) : (
                  <Copy className="h-2.5 w-2.5" />
                )}
                <span>{copied ? '已复制' : '复制'}</span>
              </button>
            </div>
            <div className="break-all text-foreground text-[10px] select-all bg-muted/40 p-1 rounded">
              {receipt.targetSha}
            </div>
            <div className="text-[10px] text-muted-foreground">
              Audit Hash: {receipt.auditPayloadHash}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
