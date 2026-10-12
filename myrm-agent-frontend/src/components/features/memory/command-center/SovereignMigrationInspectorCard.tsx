/**
 * [INPUT]
 * - @/services/memory/sovereignMigration: exportSovereignBundle, restoreSovereignBundle, detectCompetitors, ingestCompetitor
 * - @/components/primitives/card: Card, CardContent, CardDescription, CardHeader, CardTitle
 * - @/components/primitives/input: Input
 * - @/components/primitives/button: Button
 * - @/components/features/memory/command-center/CompetitorAssetDetectionView: CompetitorAssetDetectionView
 *
 * [OUTPUT]
 * - SovereignMigrationInspectorCard: Primary card for sovereign asset packaging, restore, and competitor migration.
 *
 * [POS]
 * Management card in Memory CommandCenter for full sovereign asset portability and cross-host restore.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useState } from 'react';
import {
  AlertCircle,
  Archive,
  ArrowRightLeft,
  CheckCircle2,
  FolderSearch,
  HardDriveDownload,
  HardDriveUpload,
  Loader2,
  ShieldCheck,
} from 'lucide-react';

import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/primitives/card';
import { Input } from '@/components/primitives/input';
import { CompetitorAssetDetectionView } from './CompetitorAssetDetectionView';
import {
  detectCompetitors,
  exportSovereignBundle,
  ingestCompetitor,
  restoreSovereignBundle,
  type CompetitorDetectResponseDTO,
  type CompetitorIngestResponseDTO,
  type ExportBundleResponseDTO,
  type RestoreBundleResponseDTO,
} from '@/services/memory/sovereignMigration';

export function SovereignMigrationInspectorCard() {
  const [activeTab, setActiveTab] = useState<'export' | 'restore' | 'competitors'>('export');

  // Export State
  const [exportSourceDir, setExportSourceDir] = useState('');
  const [exportOutputPath, setExportOutputPath] = useState('');
  const [exportDesc, setExportDesc] = useState('Myrm digital sovereign asset backup');
  const [exportLoading, setExportLoading] = useState(false);
  const [exportResult, setExportResult] = useState<ExportBundleResponseDTO | null>(null);

  // Restore State
  const [restoreBundlePath, setRestoreBundlePath] = useState('');
  const [restoreTargetDir, setRestoreTargetDir] = useState('');
  const [restoreWorkspaceRoot, setRestoreWorkspaceRoot] = useState('');
  const [restoreLoading, setRestoreLoading] = useState(false);
  const [restoreResult, setRestoreResult] = useState<RestoreBundleResponseDTO | null>(null);

  // Competitor State
  const [detectLoading, setDetectLoading] = useState(false);
  const [detection, setDetection] = useState<CompetitorDetectResponseDTO | null>(null);
  const [ingestLoading, setIngestLoading] = useState(false);
  const [ingestResult, setIngestResult] = useState<CompetitorIngestResponseDTO | null>(null);

  const [error, setError] = useState<string | null>(null);

  const handleExport = async () => {
    setExportLoading(true);
    setError(null);
    try {
      const res = await exportSovereignBundle({
        source_dir: exportSourceDir.trim() || null,
        output_bundle_path: exportOutputPath.trim() || null,
        custom_description: exportDesc.trim() || undefined,
      });
      setExportResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '打包主权资产包失败');
    } finally {
      setExportLoading(false);
    }
  };

  const handleRestore = async () => {
    if (!restoreBundlePath.trim()) return;
    setRestoreLoading(true);
    setError(null);
    try {
      const res = await restoreSovereignBundle({
        bundle_path: restoreBundlePath.trim(),
        target_destination_dir: restoreTargetDir.trim() || null,
        current_workspace_root: restoreWorkspaceRoot.trim() || null,
      });
      setRestoreResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '还原资产包失败');
    } finally {
      setRestoreLoading(false);
    }
  };

  const handleDetectCompetitors = async () => {
    setDetectLoading(true);
    setError(null);
    try {
      const res = await detectCompetitors();
      setDetection(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '嗅探第三方智能体资产失败');
    } finally {
      setDetectLoading(false);
    }
  };

  const handleIngestCompetitor = async (competitor: string, sourcePath: string) => {
    setIngestLoading(true);
    setError(null);
    try {
      const res = await ingestCompetitor({
        competitor,
        source_path: sourcePath,
      });
      setIngestResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : '迁入第三方资产失败');
    } finally {
      setIngestLoading(false);
    }
  };

  return (
    <Card className="border-border/70 shadow-sm">
      <CardHeader className="space-y-1 pb-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Archive className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              全量数字资产主权打包、跨机无损还原与多源迁入
            </CardTitle>
          </div>
          <div className="flex items-center gap-1 rounded-lg border border-border/60 bg-muted/30 p-0.5 text-xs">
            <Button
              variant={activeTab === 'export' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('export')}
              className="h-7 text-xs px-2.5"
            >
              一键打包 (.myrmpkg)
            </Button>
            <Button
              variant={activeTab === 'restore' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('restore')}
              className="h-7 text-xs px-2.5"
            >
              跨机还原 & 重定位
            </Button>
            <Button
              variant={activeTab === 'competitors' ? 'secondary' : 'ghost'}
              size="sm"
              onClick={() => setActiveTab('competitors')}
              className="h-7 text-xs px-2.5"
            >
              第三方智能体嗅探
            </Button>
          </div>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          支持将本地记忆、知识图谱、自定义技能与规则打包为加密便携包；还原时自适应解绑原机器绝对路径并动态重映射，支持从 Hermes、Claude Code 与 Codex 一键无损迁移。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {error && (
          <div className="flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 p-2.5 text-xs text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            <span>{error}</span>
          </div>
        )}

        {/* Tab 1: Export */}
        {activeTab === 'export' && (
          <div className="space-y-3 text-xs">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="sovereign-export-source" className="font-medium text-foreground">
                  源数据目录 (Source Dir, 选填)
                </label>
                <Input
                  id="sovereign-export-source"
                  value={exportSourceDir}
                  onChange={(e) => setExportSourceDir(e.target.value)}
                  placeholder="留空默认使用当前用户全量记忆目录"
                  className="h-8 text-xs font-mono"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="sovereign-export-output" className="font-medium text-foreground">
                  目标归档文件路径 (Output Path, 选填)
                </label>
                <Input
                  id="sovereign-export-output"
                  value={exportOutputPath}
                  onChange={(e) => setExportOutputPath(e.target.value)}
                  placeholder="留空自动生成至临时导出目录"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <div className="space-y-1">
              <label htmlFor="sovereign-export-desc" className="font-medium text-foreground">
                归档备忘描述 (Description)
              </label>
              <Input
                id="sovereign-export-desc"
                value={exportDesc}
                onChange={(e) => setExportDesc(e.target.value)}
                placeholder="记录本次备份原因或设备标签..."
                className="h-8 text-xs"
              />
            </div>

            <Button
              size="sm"
              onClick={handleExport}
              disabled={exportLoading}
              className="text-xs h-8"
            >
              {exportLoading ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <HardDriveDownload className="mr-1.5 h-3.5 w-3.5" />
              )}
              一键生成主权便携包 (.myrmpkg)
            </Button>

            {exportResult && (
              <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 space-y-2">
                <div className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
                  <CheckCircle2 className="h-4 w-4" />
                  <span>主权资产包打包成功！已生成 SHA-256 完整性指纹</span>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[11px]">
                  <div>包标识: <span className="font-mono">{exportResult.package_id}</span></div>
                  <div>打包条目: <span className="font-semibold">{exportResult.asset_count}</span></div>
                  <div>未压缩大小: <span className="font-semibold">{(exportResult.total_bytes / 1024).toFixed(1)} KB</span></div>
                  <div className="truncate" title={exportResult.sha256}>
                    SHA-256: <span className="font-mono">{exportResult.sha256.slice(0, 10)}...</span>
                  </div>
                </div>
                <div className="text-[11px] font-mono text-muted-foreground break-all">
                  路径: {exportResult.bundle_path}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 2: Restore */}
        {activeTab === 'restore' && (
          <div className="space-y-3 text-xs">
            <div className="space-y-1">
              <label htmlFor="sovereign-restore-bundle" className="font-medium text-foreground">
                资产包文件路径 (Bundle Path)
              </label>
              <Input
                id="sovereign-restore-bundle"
                value={restoreBundlePath}
                onChange={(e) => setRestoreBundlePath(e.target.value)}
                placeholder="/path/to/backup.myrmpkg"
                className="h-8 text-xs font-mono"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label htmlFor="sovereign-restore-target" className="font-medium text-foreground">
                  还原目标目录 (Target Dir, 选填)
                </label>
                <Input
                  id="sovereign-restore-target"
                  value={restoreTargetDir}
                  onChange={(e) => setRestoreTargetDir(e.target.value)}
                  placeholder="留空还原至当前活动存储"
                  className="h-8 text-xs font-mono"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="sovereign-restore-ws" className="font-medium text-foreground">
                  新宿主工作区路径 (Workspace Root, 选填)
                </label>
                <Input
                  id="sovereign-restore-ws"
                  value={restoreWorkspaceRoot}
                  onChange={(e) => setRestoreWorkspaceRoot(e.target.value)}
                  placeholder="留空自动检测当前工作区进行路径转译"
                  className="h-8 text-xs font-mono"
                />
              </div>
            </div>

            <Button
              size="sm"
              onClick={handleRestore}
              disabled={restoreLoading || !restoreBundlePath.trim()}
              className="text-xs h-8"
            >
              {restoreLoading ? (
                <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
              ) : (
                <HardDriveUpload className="mr-1.5 h-3.5 w-3.5" />
              )}
              校验指纹并原子还原
            </Button>

            {restoreResult && (
              <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 space-y-2">
                <div className="flex items-center gap-1.5 font-medium text-emerald-600 dark:text-emerald-400">
                  <ShieldCheck className="h-4 w-4" />
                  <span>校验与还原成功！完成绝对路径动态重定位</span>
                </div>
                <div className="flex flex-wrap gap-2 text-[11px]">
                  <Badge variant="outline" className="border-border">
                    还原资产: {restoreResult.restored_assets.length} 项
                  </Badge>
                  <Badge variant="outline" className="border-border">
                    重映射路径: {restoreResult.remapped_paths_count} 处
                  </Badge>
                </div>
                <div className="text-[11px] space-y-0.5 text-muted-foreground font-mono">
                  <div>原宿主工作区: {restoreResult.source_workspace_root}</div>
                  <div>新宿主工作区: {restoreResult.target_workspace_root}</div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Tab 3: Competitors */}
        {activeTab === 'competitors' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Button
                size="sm"
                variant="outline"
                onClick={handleDetectCompetitors}
                disabled={detectLoading}
                className="text-xs h-8"
              >
                {detectLoading ? (
                  <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <FolderSearch className="mr-1.5 h-3.5 w-3.5" />
                )}
                嗅探本地第三方智能体资产
              </Button>
            </div>

            <CompetitorAssetDetectionView
              detection={detection}
              onIngest={handleIngestCompetitor}
              ingesting={ingestLoading}
              ingestResult={ingestResult}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
