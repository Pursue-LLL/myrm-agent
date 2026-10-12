/**
 * [INPUT]
 * - @/services/memory/codeGraph: getCodeGraphAssetMetadata, scanWorkspaceCodeGraph, analyzeCodeImpact, queryCodeSymbols
 * - @/services/memory/codeGraph: CodeGraphAssetResponse, AnalyzeImpactResponse, CodeSymbolItem, ImpactRiskLevel
 * - @/components/primitives: Card, Button, Badge, Input
 *
 * [OUTPUT]
 * - CodeGraphAssetCard: React component rendering workspace code symbol topology,
 *   pre-modification impact blast radius analysis, and symbol topology inspector.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for CodeGraph memory assets.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle,
  FileCode2,
  GitCommit,
  Network,
  RefreshCw,
  Search,
  Zap,
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
import { cn } from '@/lib/utils/classnameUtils';
import {
  analyzeCodeImpact,
  type AnalyzeImpactResponse,
  type CodeGraphAssetResponse,
  type CodeSymbolItem,
  getCodeGraphAssetMetadata,
  queryCodeSymbols,
  scanWorkspaceCodeGraph,
} from '@/services/memory/codeGraph';
import { CodeImpactReportView } from './CodeImpactReportView';

interface CodeGraphAssetCardProps {
  className?: string;
  defaultWorkspaceDir?: string;
}

export function CodeGraphAssetCard({

  className,
  defaultWorkspaceDir = '.',
}: CodeGraphAssetCardProps) {
  const [asset, setAsset] = useState<CodeGraphAssetResponse | null>(null);
  const [symbols, setSymbols] = useState<CodeSymbolItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isScanning, setIsScanning] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  const [symbolQuery, setSymbolQuery] = useState('');
  const [targetSymbol, setTargetSymbol] = useState('');
  const [targetFilePath, setTargetFilePath] = useState('');
  const [impactReport, setImpactReport] = useState<AnalyzeImpactResponse | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const loadAssetData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [assetMeta, symbolList] = await Promise.all([
        getCodeGraphAssetMetadata(),
        queryCodeSymbols({ limit: 20 }),
      ]);
      setAsset(assetMeta);
      setSymbols(symbolList.symbols);
    } catch {
      setStatusMessage('加载代码图谱记忆资产失败，请确认服务已启动');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadAssetData();
  }, [loadAssetData]);

  const handleScanWorkspace = async () => {
    setIsScanning(true);
    setStatusMessage(null);
    try {
      const res = await scanWorkspaceCodeGraph({
        workspace_dir: defaultWorkspaceDir,
        incremental: true,
      });
      setStatusMessage(
        `扫描完成：解析 ${res.scanned_files_count} 个文件，更新 ${res.indexed_symbols_count} 个符号，总符号数 ${res.total_symbols}`,
      );
      await loadAssetData();
    } catch {
      setStatusMessage('扫描工作区失败');
    } finally {
      setIsScanning(false);
    }
  };

  const handleAnalyzeImpact = async () => {
    if (!targetSymbol.trim()) return;

    setIsAnalyzing(true);
    setStatusMessage(null);
    try {
      const res = await analyzeCodeImpact({
        symbol_name: targetSymbol.trim(),
        file_path: targetFilePath.trim() || undefined,
      });
      setImpactReport(res);
      setStatusMessage(
        `影响面评估完毕：爆炸半径 ${res.blast_radius}，风险等级 ${res.risk_level}`,
      );
    } catch {
      setStatusMessage('评估代码修改影响面失败');
    } finally {
      setIsAnalyzing(false);
    }
  };



  const handleSearchSymbols = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    try {
      const res = await queryCodeSymbols({ query: symbolQuery.trim(), limit: 20 });
      setSymbols(res.symbols);
    } catch {
      setStatusMessage('检索符号失败');
    }
  };

  return (

    <Card className={cn('border-border/60 bg-card shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <Network className="h-5 w-5 text-indigo-500" />
            <CardTitle className="text-base font-semibold">
              代码图谱与修改影响面评估 (CodeGraph & Impact Analysis)
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleScanWorkspace}
              disabled={isScanning || isLoading}
              className="h-8 gap-1 text-xs"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isScanning && 'animate-spin')} />
              增量扫描工作区
            </Button>
          </div>
        </div>
        <CardDescription className="text-xs">
          腾讯云 TencentDB Memory 架构标准：将工作区 AST
          代码拓扑持久化为长期记忆资产，修改前自动计算爆炸半径与波及调用链。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* HUD Metadata Overview */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div className="rounded-lg border border-border/50 bg-accent/20 p-2.5">
            <span className="text-[11px] text-muted-foreground">存储库标识</span>
            <div className="mt-1 truncate font-mono text-xs font-semibold text-foreground">
              {asset?.repo_id || 'myrm_workspace'}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-accent/20 p-2.5">
            <span className="text-[11px] text-muted-foreground">已注册符号数</span>
            <div className="mt-1 text-sm font-semibold text-foreground">
              {asset?.total_symbols ?? 0}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-accent/20 p-2.5">
            <span className="text-[11px] text-muted-foreground">拓扑调用边数</span>
            <div className="mt-1 text-sm font-semibold text-foreground">
              {asset?.total_edges ?? 0}
            </div>
          </div>
          <div className="rounded-lg border border-border/50 bg-accent/20 p-2.5">
            <span className="text-[11px] text-muted-foreground">快照版本哈希</span>
            <div className="mt-1 flex items-center gap-1 font-mono text-xs text-foreground">
              <GitCommit className="h-3 w-3 text-muted-foreground" />
              {asset?.version_hash ? asset.version_hash.slice(0, 8) : 'clean'}
            </div>
          </div>
        </div>

        {/* Pre-Modification Impact Analysis Section */}
        <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="mb-2 flex items-center gap-2">
            <Zap className="h-4 w-4 text-amber-500" />
            <span className="text-xs font-semibold text-foreground">
              智能体修改前影响面评估 (Blast Radius Guard)
            </span>
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              void handleAnalyzeImpact();
            }}
            className="flex flex-wrap items-center gap-2"
          >
            <Input
              value={targetSymbol}
              onChange={(e) => setTargetSymbol(e.target.value)}
              placeholder="待修改符号名 (如 helper_calculate)"
              className="h-8 min-w-[200px] flex-1 text-xs"
            />
            <Input
              value={targetFilePath}
              onChange={(e) => setTargetFilePath(e.target.value)}
              placeholder="文件路径 (可选)"
              className="h-8 w-44 text-xs"
            />
            <Button
              type="button"
              size="sm"
              onClick={() => void handleAnalyzeImpact()}
              disabled={isAnalyzing || !targetSymbol.trim()}
              className="h-8 gap-1 text-xs"
            >
              <Zap className={cn('h-3.5 w-3.5', isAnalyzing && 'animate-spin')} />
              评估影响面
            </Button>
          </form>


          {impactReport && <CodeImpactReportView report={impactReport} />}

        </div>

        {/* Symbol Topology Search & Preview Inspector */}
        <div className="rounded-lg border border-border/70 bg-card p-3 shadow-xs">
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <FileCode2 className="h-4 w-4 text-blue-500" />
              <span className="text-xs font-semibold text-foreground">
                符号拓扑资产探针 ({symbols.length})
              </span>
            </div>
            <form onSubmit={handleSearchSymbols} className="flex items-center gap-1.5">
              <Input
                value={symbolQuery}
                onChange={(e) => setSymbolQuery(e.target.value)}
                placeholder="过滤符号..."
                className="h-7 w-36 text-xs"
              />
              <Button type="submit" variant="ghost" size="sm" className="h-7 px-2">
                <Search className="h-3.5 w-3.5" />
              </Button>
            </form>
          </div>

          <div className="grid max-h-44 gap-1.5 overflow-y-auto sm:grid-cols-2">
            {symbols.map((sym) => (
              <button
                key={sym.symbol_id}
                type="button"
                onClick={() => {
                  setTargetSymbol(sym.name);
                  setTargetFilePath(sym.file_path);
                }}
                className="flex items-start justify-between rounded border border-border/40 bg-accent/15 p-2 text-left transition hover:bg-accent/30"
              >
                <div className="min-w-0 pr-2">
                  <div className="truncate font-mono text-xs font-semibold text-foreground">
                    {sym.name}
                  </div>
                  <div className="truncate text-[10px] text-muted-foreground">
                    {sym.file_path}:{sym.line_start}
                  </div>
                </div>
                <Badge variant="outline" className="shrink-0 text-[9px]">
                  {sym.kind}
                </Badge>
              </button>
            ))}
          </div>
        </div>

        {/* Status Notification Message */}
        {statusMessage && (
          <div className="flex items-center gap-2 rounded-md border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
            {statusMessage.includes('失败') ? (
              <AlertTriangle className="h-4 w-4 text-destructive" />
            ) : (
              <CheckCircle className="h-4 w-4 text-emerald-500" />
            )}
            <span>{statusMessage}</span>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
