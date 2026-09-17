'use client';

/**
 * [INPUT]
 * @/services/memory/domainMesh::getMemoryDrillDown, DrillDownResponse
 * @/components/primitives/dialog::Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription
 * lucide-react::Layers, Copy, Check, Calendar, Tag, ShieldCheck, Loader2
 *
 * [OUTPUT]
 * MemoryDrillDownDialog: Modal displaying progressive L0/L1/L2 drill-down details and verbatim evidence.
 *
 * [POS]
 * Modal layer for single-memory inspection.
 */

import React, { useEffect, useState } from 'react';
import { Layers, Copy, Check, Calendar, Tag, Loader2, Sparkles } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/primitives/dialog';
import { getMemoryDrillDown, type DrillDownResponse } from '@/services/memory/domainMesh';

interface MemoryDrillDownDialogProps {
  memoryId: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export const MemoryDrillDownDialog: React.FC<MemoryDrillDownDialogProps> = ({
  memoryId,
  open,
  onOpenChange,
}) => {
  const [detail, setDetail] = useState<DrillDownResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open || !memoryId) {
      setDetail(null);
      return;
    }

    let active = true;
    setLoading(true);
    getMemoryDrillDown(memoryId)
      .then((res) => {
        if (active) {
          setDetail(res);
        }
      })
      .catch(() => {
        if (active) {
          setDetail(null);
        }
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [open, memoryId]);

  const handleCopy = () => {
    if (!detail?.l2_content) {
      return;
    }
    navigator.clipboard.writeText(detail.l2_content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl sm:max-w-2xl max-h-[85vh] flex flex-col overflow-hidden">
        <DialogHeader>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Sparkles className="h-3.5 w-3.5" />
            Progressive Memory Drill-Down
          </div>
          <DialogTitle className="text-base font-semibold leading-snug">
            {detail?.l0 || (loading ? 'Loading memory details...' : 'Memory Not Found')}
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground flex flex-wrap items-center gap-2 pt-1">
            {detail && (
              <>
                <span className="inline-flex items-center gap-1 rounded bg-accent/60 px-1.5 py-0.5 font-medium capitalize">
                  <Tag className="h-3 w-3" />
                  {detail.domain} / {detail.category}
                </span>
                <span className="inline-flex items-center gap-1 rounded bg-accent/60 px-1.5 py-0.5">
                  <Layers className="h-3 w-3" />
                  {detail.memory_type}
                </span>
                {detail.updated_at && (
                  <span className="inline-flex items-center gap-1 text-[11px]">
                    <Calendar className="h-3 w-3" />
                    {new Date(detail.updated_at).toLocaleString()}
                  </span>
                )}
              </>
            )}
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <Loader2 className="h-6 w-6 animate-spin text-primary" />
          </div>
        ) : detail ? (
          <div className="flex flex-1 flex-col gap-4 overflow-y-auto pr-1 text-xs">
            {/* L1 Overview */}
            {detail.l1 && (
              <div className="rounded-lg border border-border/60 bg-accent/20 p-3">
                <div className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-1">
                  L1 Overview (Digest)
                </div>
                <p className="text-foreground/90 leading-relaxed">{detail.l1}</p>
              </div>
            )}

            {/* L2 Full Verbatim Body */}
            <div className="flex flex-1 flex-col rounded-lg border border-border/80 bg-muted/30 p-3">
              <div className="flex items-center justify-between pb-2 border-b border-border/40">
                <span className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  L2 Verbatim Ground Truth & Evidence
                </span>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="inline-flex items-center gap-1 rounded border border-border/60 bg-background px-2 py-1 text-[11px] font-medium text-foreground hover:bg-accent transition-colors"
                >
                  {copied ? (
                    <>
                      <Check className="h-3 w-3 text-emerald-500" />
                      <span>Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3 w-3" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
              <pre className="mt-2 flex-1 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-foreground/90 break-all">
                {detail.l2_content}
              </pre>
            </div>
          </div>
        ) : (
          <div className="p-8 text-center text-xs text-muted-foreground">
            Unable to load verbatim details for memory ID {memoryId}.
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
};
