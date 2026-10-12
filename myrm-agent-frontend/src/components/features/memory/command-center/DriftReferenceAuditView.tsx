/**
 * [INPUT]
 * - @/services/memory/driftDefense: DriftCheckResponseDTO, BatchDriftCheckResponseDTO, MemoryDriftFindingDTO
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - DriftReferenceAuditView: Sub-component rendering ground truth verification findings and stale warnings.
 *
 * [POS]
 * Sub-component for GroundTruthDriftDefenseCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  FileCode,
  FileX,
  History,
  Layers,
  ShieldAlert,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import type {
  BatchDriftCheckResponseDTO,
  DriftCheckResponseDTO,
  MemoryDriftFindingDTO,
} from '@/services/memory/driftDefense';

interface DriftReferenceAuditViewProps {
  singleResult?: DriftCheckResponseDTO | null;
  batchResult?: BatchDriftCheckResponseDTO | null;
}

function getDriftTypeBadge(driftType: string): { label: string; className: string } {
  switch (driftType) {
    case 'file_not_found':
      return {
        label: '物理文件缺失 (file_not_found)',
        className: 'border-destructive/40 text-destructive bg-destructive/10',
      };
    case 'symbol_not_found':
      return {
        label: '函数/类符号缺失 (symbol_not_found)',
        className: 'border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10',
      };
    case 'file_content_drift':
      return {
        label: '文件内容演进 (file_content_drift)',
        className: 'border-blue-500/40 text-blue-600 dark:text-blue-400 bg-blue-500/10',
      };
    case 'config_changed':
      return {
        label: '配置变更漂移 (config_changed)',
        className: 'border-purple-500/40 text-purple-600 dark:text-purple-400 bg-purple-500/10',
      };
    default:
      return {
        label: driftType,
        className: 'border-muted-foreground/40 text-muted-foreground bg-muted/20',
      };
  }
}

function FindingItem({ finding }: { finding: MemoryDriftFindingDTO }) {
  const badgeInfo = getDriftTypeBadge(finding.drift_type);
  return (
    <div className="rounded border border-border/60 bg-muted/30 p-2.5 text-xs space-y-1">
      <div className="flex flex-wrap items-center justify-between gap-1.5">
        <Badge variant="outline" className={`text-[10px] ${badgeInfo.className}`}>
          {badgeInfo.label}
        </Badge>
        <span className="font-mono text-muted-foreground truncate max-w-[200px]">
          {finding.reference_target}
        </span>
      </div>
      <p className="text-foreground/90">{finding.detail}</p>
    </div>
  );
}

export function DriftReferenceAuditView({
  singleResult,
  batchResult,
}: DriftReferenceAuditViewProps) {
  if (!singleResult && !batchResult) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        暂无代码真实性漂移检测记录，请填写待校验记忆或发起批量检测
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {singleResult && (
        <div className="rounded-md border border-border/70 bg-card p-3.5 text-xs space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
            <div className="flex items-center gap-1.5 font-medium">
              {singleResult.is_drifted ? (
                <ShieldAlert className="h-4 w-4 text-destructive" />
              ) : (
                <ShieldCheck className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
              )}
              <span>单项物理校验: {singleResult.memory_id}</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={
                  singleResult.is_drifted
                    ? 'border-destructive/40 text-destructive bg-destructive/10'
                    : 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                }
              >
                {singleResult.is_drifted ? '检测到代码漂移' : '与源码完全一致'}
              </Badge>
              {singleResult.confidence_penalty > 0 && (
                <Badge variant="outline" className="border-amber-500/40 text-amber-600 dark:text-amber-400 bg-amber-500/10">
                  置信度扣减 -{Math.round(singleResult.confidence_penalty * 100)}%
                </Badge>
              )}
            </div>
          </div>

          {/* Findings */}
          {singleResult.findings.length > 0 ? (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1 font-medium text-destructive">
                <AlertTriangle className="h-3.5 w-3.5" />
                <span>物理不一致证据 ({singleResult.findings.length} 处)</span>
              </div>
              <div className="space-y-1.5">
                {singleResult.findings.map((finding, idx) => (
                  <FindingItem key={`${finding.reference_target}-${idx}`} finding={finding} />
                ))}
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 text-xs">
              <CheckCircle2 className="h-3.5 w-3.5" />
              <span>所有引用的物理文件及 AST 符号均在当前工作区真实存在。</span>
            </div>
          )}

          {/* Decorated Content */}
          <div className="space-y-1 pt-1">
            <div className="flex items-center gap-1 font-medium text-muted-foreground">
              <FileCode className="h-3.5 w-3.5" />
              <span>注入前装配效果 (Prompt-Decorated Preview)</span>
            </div>
            <pre className="max-h-36 overflow-auto rounded bg-muted/50 p-2 font-mono text-[11px] leading-relaxed text-foreground whitespace-pre-wrap">
              {singleResult.decorated_content}
            </pre>
          </div>
        </div>
      )}

      {batchResult && (
        <div className="rounded-md border border-border/70 bg-card p-3.5 text-xs space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
            <div className="flex items-center gap-1.5 font-medium">
              <Layers className="h-4 w-4 text-primary" />
              <span>批量漂移防护沙盒统计</span>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="border-border">
                评估总量: {batchResult.total_checked}
              </Badge>
              <Badge
                variant="outline"
                className={
                  batchResult.drifted_count > 0
                    ? 'border-destructive/40 text-destructive bg-destructive/10'
                    : 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                }
              >
                漂移拦截: {batchResult.drifted_count}
              </Badge>
            </div>
          </div>

          <div className="space-y-2">
            {batchResult.results.map((res) => (
              <div
                key={res.memory_id}
                className="flex items-center justify-between rounded border border-border/40 bg-muted/20 px-2.5 py-1.5 text-xs"
              >
                <div className="flex items-center gap-2 truncate">
                  {res.is_drifted ? (
                    <FileX className="h-3.5 w-3.5 text-destructive shrink-0" />
                  ) : (
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0" />
                  )}
                  <span className="font-mono">{res.memory_id}</span>
                  {res.findings.length > 0 && (
                    <span className="text-[11px] text-muted-foreground truncate">
                      ({res.findings[0].detail})
                    </span>
                  )}
                </div>
                <Badge
                  variant="outline"
                  className={
                    res.is_drifted
                      ? 'border-destructive/40 text-destructive text-[10px]'
                      : 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 text-[10px]'
                  }
                >
                  {res.is_drifted ? `漂移 (-${Math.round(res.confidence_penalty * 100)}%)` : '有效'}
                </Badge>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
