/**
 * [INPUT]
 * - @/services/memory/codeGraph: AnalyzeImpactResponse, ImpactRiskLevel
 * - @/components/primitives/badge: Badge
 *
 * [OUTPUT]
 * - CodeImpactReportView: Presentational component rendering pre-modification blast radius,
 *   risk level badges, direct/indirect callers, and safety precautions.
 *
 * [POS]
 * Sub-component for CodeGraphAssetCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import { Code2, ShieldAlert } from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import type { AnalyzeImpactResponse, ImpactRiskLevel } from '@/services/memory/codeGraph';

interface CodeImpactReportViewProps {
  report: AnalyzeImpactResponse;
}

export function getRiskBadge(level: ImpactRiskLevel): { label: string; className: string } {
  switch (level.toUpperCase()) {
    case 'CRITICAL':
      return { label: 'CRITICAL 严重波及', className: 'bg-rose-600 text-white' };
    case 'HIGH':
      return { label: 'HIGH 高风险', className: 'bg-amber-600 text-white' };
    case 'MEDIUM':
      return { label: 'MEDIUM 中风险', className: 'bg-yellow-600 text-white' };
    default:
      return { label: 'LOW 安全范围', className: 'bg-emerald-600 text-white' };
  }
}

export function CodeImpactReportView({ report }: CodeImpactReportViewProps) {
  const riskBadge = getRiskBadge(report.risk_level);

  return (
    <div className="mt-3 space-y-2.5 rounded-md border border-border/60 bg-accent/10 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-mono text-xs font-medium text-foreground">
          <Code2 className="h-3.5 w-3.5 text-primary" />
          <span>{report.target_symbol_name}</span>
          {report.file_path && (
            <span className="text-muted-foreground">({report.file_path})</span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-muted-foreground">
            爆炸半径分值: <strong>{report.blast_radius}</strong>
          </span>
          <Badge className={cn('px-2 py-0.5 text-[10px]', riskBadge.className)}>
            {riskBadge.label}
          </Badge>
        </div>
      </div>

      {/* Direct & Indirect Callers */}
      <div className="grid gap-2 text-xs sm:grid-cols-2">
        <div className="rounded border border-border/40 bg-card/60 p-2">
          <div className="font-semibold text-foreground">
            直接调用方 ({report.direct_callers.length})
          </div>
          {report.direct_callers.length > 0 ? (
            <ul className="mt-1 max-h-24 space-y-0.5 overflow-y-auto font-mono text-[11px] text-muted-foreground">
              {report.direct_callers.map((caller) => (
                <li key={caller} className="truncate">
                  • {caller}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-1 text-[11px] text-muted-foreground">无直接依赖调用</div>
          )}
        </div>

        <div className="rounded border border-border/40 bg-card/60 p-2">
          <div className="font-semibold text-foreground">
            间接多跳调用方 ({report.indirect_callers.length})
          </div>
          {report.indirect_callers.length > 0 ? (
            <ul className="mt-1 max-h-24 space-y-0.5 overflow-y-auto font-mono text-[11px] text-muted-foreground">
              {report.indirect_callers.map((caller) => (
                <li key={caller} className="truncate">
                  • {caller}
                </li>
              ))}
            </ul>
          ) : (
            <div className="mt-1 text-[11px] text-muted-foreground">无间接级联依赖</div>
          )}
        </div>
      </div>

      {/* Safety Recommendations */}
      {report.safety_recommendations.length > 0 && (
        <div className="rounded border border-border/40 bg-card/60 p-2 text-xs">
          <div className="flex items-center gap-1 font-semibold text-foreground">
            <ShieldAlert className="h-3.5 w-3.5 text-amber-500" />
            <span>安全建议 (Safety Guard)</span>
          </div>
          <ul className="mt-1 space-y-0.5 text-[11px] text-muted-foreground">
            {report.safety_recommendations.map((rec, idx) => (
              <li key={idx}>• {rec}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
