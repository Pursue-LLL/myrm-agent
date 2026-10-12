/**
 * [INPUT]
 * - @/services/memory/experienceGene: listExperienceGenes, getExperienceGeneStats, queryGeneMutationAdvice, penalizeExperienceGene, extractCausalGenes
 * - @/services/memory/experienceGene: ExperienceGeneResponse, GeneLedgerStatsResponse, GeneMutationAdviceResponse
 * - @/components/primitives: Card, Button, Badge, Input
 * - ./GeneAdviceListView: GeneAdviceListView
 *
 * [OUTPUT]
 * - GeneEvolutionInspectorCard: React container rendering Causal Experience Genes,
 *   Darwinian confidence evolution ledger, planning advice probe, and failure penalization.
 *
 * [POS]
 * Personal Brain Command Center UnderstandSection card for experience gene evolution.
 * Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  Award,
  CheckCircle,
  Dna,
  Flame,
  MinusCircle,
  RotateCcw,
  Search,
  Sparkles,
  TrendingUp,
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
  type ExperienceGeneResponse,
  extractCausalGenes,
  type GeneLedgerStatsResponse,
  type GeneMutationAdviceResponse,
  getExperienceGeneStats,
  listExperienceGenes,
  penalizeExperienceGene,
  queryGeneMutationAdvice,
} from '@/services/memory/experienceGene';
import { GeneAdviceListView } from './GeneAdviceListView';

interface GeneEvolutionInspectorCardProps {
  className?: string;
}

export function GeneEvolutionInspectorCard({ className }: GeneEvolutionInspectorCardProps) {
  const [stats, setStats] = useState<GeneLedgerStatsResponse | null>(null);
  const [genes, setGenes] = useState<ExperienceGeneResponse[]>([]);
  const [advices, setAdvices] = useState<GeneMutationAdviceResponse[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isQuerying, setIsQuerying] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  // Probe inputs
  const [probeSignals, setProbeSignals] = useState('kernel_panic, driver_deadlock');
  const [minConfidence, setMinConfidence] = useState(0.6);

  // Extraction simulator inputs
  const [simTaskGoal, setSimTaskGoal] = useState('Fix permission denied on build cache');
  const [simToolName, setSimToolName] = useState('bash');
  const [simErrorSignature, setSimErrorSignature] = useState('permission_denied: operation not permitted');
  const [simResolution, setSimResolution] = useState('Chmod user group before executing clean command');

  const loadData = useCallback(async () => {
    setIsLoading(true);
    try {
      const [statsRes, genesRes] = await Promise.all([
        getExperienceGeneStats(),
        listExperienceGenes(),
      ]);
      setStats(statsRes);
      setGenes(genesRes);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '加载经验基因数据失败';
      setStatusMessage(`错误: ${message}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleQueryAdvice = async () => {
    setIsQuerying(true);
    setStatusMessage(null);
    try {
      const signals = probeSignals
        .split(',')
        .map((s) => s.trim())
        .filter(Boolean);
      const res = await queryGeneMutationAdvice({
        active_signals: signals,
        min_confidence: minConfidence,
        limit: 5,
      });
      setAdvices(res.advices);
      setStatusMessage(`已匹配 ${res.total_matched} 条因果经验基因`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '探针查询失败';
      setStatusMessage(`错误: ${message}`);
    } finally {
      setIsQuerying(false);
    }
  };

  const handlePenalize = async (geneId: string) => {
    try {
      const updated = await penalizeExperienceGene({ gene_id: geneId, penalty: 0.2 });
      if (updated) {
        setStatusMessage(`已对基因 ${geneId} 扣减置信度 (当前: ${(updated.confidence_score * 100).toFixed(0)}%)`);
        await loadData();
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '扣减惩罚失败';
      setStatusMessage(`错误: ${message}`);
    }
  };

  const handleSimulateExtraction = async () => {
    setStatusMessage(null);
    try {
      const res = await extractCausalGenes({
        trace: {
          session_id: `sim-session-${Date.now()}`,
          task_goal: simTaskGoal,
          domain_tag: 'system_dev',
          success_verified: true,
          final_solution_summary: simResolution,
          steps: [
            {
              step_index: 1,
              tool_name: simToolName,
              tool_input_summary: 'execute initial command',
              is_failure: true,
              error_signature: simErrorSignature,
            },
            {
              step_index: 2,
              tool_name: 'fix_permissions',
              tool_input_summary: simResolution,
              is_failure: false,
            },
          ],
        },
      });
      if (res.gene) {
        setStatusMessage(`成功合成因果经验基因: ${res.gene.gene_id} (验证次数: ${res.gene.proof_count})`);
        await loadData();
      } else {
        setStatusMessage('未从当前轨迹中提取到有效因果基因');
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : '合成经验基因失败';
      setStatusMessage(`错误: ${message}`);
    }
  };

  return (
    <Card className={cn('border-border/80 shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Dna className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              因果经验基因合成器与达尔文演化账本
            </CardTitle>
          </div>
          <div className="flex items-center gap-2">
            <Badge variant="outline" className="border-primary/40 text-primary text-xs">
              EvoX 达尔文自进化
            </Badge>
            <Button
              size="icon"
              variant="ghost"
              className="h-7 w-7 text-muted-foreground"
              onClick={loadData}
              disabled={isLoading}
              title="刷新数据"
            >
              <RotateCcw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
            </Button>
          </div>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          将长程多轮攻坚中验证的因果规律沉淀为经验基因（前置征兆 ➔ 证伪死胡同 ➔ 验证解法），任务规划期前置注入以杜绝重复踩坑
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* KPI 指标栏 */}
        {stats && (
          <div className="grid grid-cols-3 gap-2 rounded-lg border border-border/60 bg-muted/30 p-2.5 text-center">
            <div>
              <div className="text-[10px] text-muted-foreground">累计沉淀基因</div>
              <div className="font-mono text-sm font-semibold text-foreground">
                {stats.total_genes} 条
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">平均演化置信度</div>
              <div className="flex items-center justify-center gap-0.5 font-mono text-sm font-semibold text-primary">
                <TrendingUp className="h-3.5 w-3.5" />
                {(stats.avg_confidence * 100).toFixed(0)}%
              </div>
            </div>
            <div>
              <div className="text-[10px] text-muted-foreground">跨任务验证总次数</div>
              <div className="flex items-center justify-center gap-0.5 font-mono text-sm font-semibold text-emerald-600 dark:text-emerald-400">
                <Award className="h-3.5 w-3.5" />
                {stats.total_proof_count} 次
              </div>
            </div>
          </div>
        )}

        {/* 探针查询区 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
          <div className="md:col-span-2 space-y-1">
            <label
              htmlFor="gene-probe-signals-input"
              className="text-[11px] font-medium text-muted-foreground flex items-center gap-1"
            >
              <Zap className="h-3 w-3" /> 前置征兆信号 (逗号分隔)
            </label>
            <Input
              id="gene-probe-signals-input"
              value={probeSignals}
              onChange={(e) => setProbeSignals(e.target.value)}
              placeholder="e.g. permission_denied, deadlock"
              className="h-8 font-mono text-xs"
            />
          </div>
          <div className="space-y-1">
            <label
              htmlFor="gene-probe-confidence-input"
              className="text-[11px] font-medium text-muted-foreground flex items-center gap-1"
            >
              <Flame className="h-3 w-3" /> 最低置信度门限
            </label>
            <div className="flex items-center gap-2">
              <Input
                id="gene-probe-confidence-input"
                type="number"
                step="0.05"
                min="0.1"
                max="1.0"
                value={minConfidence}
                onChange={(e) => setMinConfidence(Number(e.target.value) || 0.6)}
                className="h-8 font-mono text-xs"
              />
              <Button
                size="sm"
                disabled={isQuerying || !probeSignals.trim()}
                onClick={handleQueryAdvice}
                className="h-8 shrink-0 text-xs"
              >
                <Search className="mr-1 h-3.5 w-3.5" />
                探针匹配
              </Button>
            </div>
          </div>
        </div>

        {/* 规划期命中建议视图 */}
        <GeneAdviceListView advices={advices} />

        {/* 基因沉淀总账本 */}
        <div className="space-y-2 pt-2 border-t border-border/50">
          <div className="text-[11px] font-medium text-muted-foreground flex items-center justify-between">
            <span>经验基因演化总览 ({genes.length})</span>
          </div>
          {genes.length === 0 ? (
            <div className="rounded border border-dashed border-border/60 p-3 text-center text-xs text-muted-foreground">
              暂无已沉淀的因果基因
            </div>
          ) : (
            <div className="max-h-48 space-y-2 overflow-y-auto pr-1">
              {genes.map((g) => (
                <div
                  key={g.gene_id}
                  className="rounded border border-border/70 bg-card p-2 text-xs flex items-center justify-between gap-2"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 font-mono text-[11px]">
                      <span className="font-semibold text-foreground">{g.gene_id}</span>
                      <Badge variant="outline" className="text-[10px] py-0">
                        证明 {g.proof_count} 次
                      </Badge>
                      <span className="text-[10px] text-muted-foreground font-mono">
                        置信度: {(g.confidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1 truncate text-muted-foreground text-[10px]">
                      <strong>解法:</strong> {g.proven_resolution}
                    </div>
                  </div>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => handlePenalize(g.gene_id)}
                    className="h-7 px-2 text-[10px] text-destructive hover:bg-destructive/10 shrink-0"
                    title="降低置信度"
                  >
                    <MinusCircle className="mr-1 h-3 w-3" />
                    惩罚降权
                  </Button>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 轨迹提取实验台 */}
        <div className="space-y-2 pt-2 border-t border-border/50">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-medium text-muted-foreground flex items-center gap-1">
              <Sparkles className="h-3 w-3 text-primary" /> 经验基因合成实验台
            </span>
            <Button
              size="sm"
              variant="outline"
              onClick={handleSimulateExtraction}
              className="h-7 text-xs"
            >
              一键提取基因
            </Button>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            <div className="space-y-1">
              <label
                htmlFor="gene-sim-goal-input"
                className="text-[10px] text-muted-foreground"
              >
                任务目标
              </label>
              <Input
                id="gene-sim-goal-input"
                value={simTaskGoal}
                onChange={(e) => setSimTaskGoal(e.target.value)}
                className="h-7 font-mono text-[11px]"
              />
            </div>
            <div className="space-y-1">
              <label
                htmlFor="gene-sim-error-input"
                className="text-[10px] text-muted-foreground"
              >
                失败错误特征
              </label>
              <Input
                id="gene-sim-error-input"
                value={simErrorSignature}
                onChange={(e) => setSimErrorSignature(e.target.value)}
                className="h-7 font-mono text-[11px]"
              />
            </div>
          </div>
        </div>

        {statusMessage && (
          <div className="rounded bg-accent/40 px-2.5 py-1.5 text-[11px] text-muted-foreground">
            {statusMessage}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
