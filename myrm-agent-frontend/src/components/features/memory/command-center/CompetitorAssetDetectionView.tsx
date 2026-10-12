/**
 * [INPUT]
 * - @/services/memory/sovereignMigration: CompetitorDetectResponseDTO, CompetitorIngestResponseDTO
 * - @/components/primitives/badge: Badge
 * - @/components/primitives/button: Button
 *
 * [OUTPUT]
 * - CompetitorAssetDetectionView: Sub-component rendering detected third-party assistant assets and one-click ingestion.
 *
 * [POS]
 * Sub-component for SovereignMigrationInspectorCard under command-center.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React from 'react';
import {
  CheckCircle2,
  Download,
  FolderSearch,
  HardDrive,
  Loader2,
  Sparkles,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import type {
  CompetitorDetectResponseDTO,
  CompetitorIngestResponseDTO,
} from '@/services/memory/sovereignMigration';

interface CompetitorAssetDetectionViewProps {
  detection: CompetitorDetectResponseDTO | null;
  onIngest: (competitor: string, sourcePath: string) => Promise<void>;
  ingesting: boolean;
  ingestResult: CompetitorIngestResponseDTO | null;
}

export function CompetitorAssetDetectionView({
  detection,
  onIngest,
  ingesting,
  ingestResult,
}: CompetitorAssetDetectionViewProps) {
  if (!detection) {
    return (
      <div className="rounded border border-dashed border-border/60 p-4 text-center text-xs text-muted-foreground">
        点击下方“嗅探本地第三方智能体资产”即可自动探测本机 Hermes、Claude Code 或 Codex 的历史配置与记忆
      </div>
    );
  }

  const items = [
    {
      key: 'hermes',
      name: 'Hermes Agent',
      desc: '记忆、自定义技能与 config.yaml',
      path: detection.hermes_dir,
      detected: Boolean(detection.hermes_dir),
    },
    {
      key: 'claude_code',
      name: 'Claude Code',
      desc: 'CLAUDE.md 项目/全局规则与指令',
      path: detection.claude_code_rule_path,
      detected: Boolean(detection.claude_code_rule_path),
    },
    {
      key: 'codex',
      name: 'Codex / OpenClaw',
      desc: 'AGENTS.md 多智能体统一规则与技能集',
      path: detection.codex_rule_path,
      detected: Boolean(detection.codex_rule_path),
    },
  ];

  return (
    <div className="space-y-3">
      <div className="rounded-md border border-border/70 bg-card p-3.5 text-xs space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border/50 pb-2">
          <div className="flex items-center gap-1.5 font-medium">
            <FolderSearch className="h-4 w-4 text-primary" />
            <span>本机第三方智能体资产嗅探结果</span>
          </div>
          <Badge
            variant="outline"
            className={
              detection.detected_competitors.length > 0
                ? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10'
                : 'border-muted-foreground/40 text-muted-foreground'
            }
          >
            已探测到 {detection.detected_competitors.length} 处来源
          </Badge>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
          {items.map((item) => (
            <div
              key={item.key}
              className={`rounded border p-2.5 text-xs space-y-2 transition-colors ${
                item.detected
                  ? 'border-primary/40 bg-primary/5'
                  : 'border-border/40 bg-muted/20 opacity-70'
              }`}
            >
              <div className="flex items-center justify-between gap-1.5">
                <span className="font-semibold text-foreground">{item.name}</span>
                <Badge
                  variant="outline"
                  className={
                    item.detected
                      ? 'border-emerald-500/40 text-emerald-600 dark:text-emerald-400 text-[10px]'
                      : 'border-border text-muted-foreground text-[10px]'
                  }
                >
                  {item.detected ? '已发现' : '未安装'}
                </Badge>
              </div>
              <p className="text-[11px] text-muted-foreground">{item.desc}</p>
              {item.path ? (
                <p className="font-mono text-[10px] text-muted-foreground truncate" title={item.path}>
                  {item.path}
                </p>
              ) : null}
              {item.detected && item.path && (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={ingesting}
                  onClick={() => onIngest(item.key, item.path!)}
                  className="w-full text-[11px] h-7 mt-1"
                >
                  {ingesting ? (
                    <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                  ) : (
                    <Download className="mr-1 h-3 w-3" />
                  )}
                  一键无损迁入 Myrm
                </Button>
              )}
            </div>
          ))}
        </div>

        {ingestResult && (
          <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-xs space-y-1.5">
            <div className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
              <CheckCircle2 className="h-4 w-4" />
              <span>迁入转换完成！数据资产已无损录入 Myrm 记忆与技能体系</span>
            </div>
            <div className="flex flex-wrap gap-2 pt-1">
              <Badge variant="outline" className="border-border bg-background/50">
                记忆转译: {ingestResult.imported_memories_count} 条
              </Badge>
              <Badge variant="outline" className="border-border bg-background/50">
                技能转译: {ingestResult.imported_skills_count} 个
              </Badge>
              <Badge variant="outline" className="border-border bg-background/50">
                规则转译: {ingestResult.imported_rules_count} 项
              </Badge>
            </div>
            {ingestResult.details.length > 0 && (
              <ul className="list-disc list-inside text-[11px] text-muted-foreground space-y-0.5 pt-1">
                {ingestResult.details.map((detail, idx) => (
                  <li key={idx}>{detail}</li>
                ))}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
