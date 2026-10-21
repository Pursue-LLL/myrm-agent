/**
 * Retrieval Score Honesty and Raw vs Ranking Inspection Card (Item 142).
 * Interactive dashboard providing dual-threshold calibration, white-box factor
 * breakdowns, and divergence diagnostics between vector similarity and ranking scores.
 */

import React, { useState, useEffect, useCallback } from 'react';
import {
  SlidersHorizontal,
  Scale,
  ShieldAlert,
  ShieldCheck,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  Info,
} from 'lucide-react';
import {
  scoreHonestyService,
  CandidateEvaluationItemDTO,
  HonestCandidateResponseDTO,
  ScoreHonestyStatsDTO,
} from '@/services/memory/scoreHonesty';

const defaultCandidates: CandidateEvaluationItemDTO[] = [
  {
    id: 'cand-001',
    content: '用户在 Postgres 数据库中对大表查询开启并行扫描优化',
    raw_similarity: 0.88,
    recency_factor: 1.15,
    importance_boost: 1.1,
    mmr_penalty: 0.05,
    rrf_score: 0.02,
  },
  {
    id: 'cand-002',
    content: '昨日临时调试日志：Qdrant 向量维度采样飞行前自愈通过',
    raw_similarity: 0.35,
    recency_factor: 1.85,
    importance_boost: 1.2,
    mmr_penalty: 0.0,
    rrf_score: 0.03,
  },
  {
    id: 'cand-003',
    content: '三个月前的历史架构说明：Docker 容器 IPv4 本地回环地址规范化',
    raw_similarity: 0.76,
    recency_factor: 0.45,
    importance_boost: 0.9,
    mmr_penalty: 0.1,
    rrf_score: 0.01,
  },
  {
    id: 'cand-004',
    content: '随手记录的生活备忘：周末买牛奶与咖啡豆',
    raw_similarity: 0.12,
    recency_factor: 0.6,
    importance_boost: 0.5,
    mmr_penalty: 0.3,
    rrf_score: 0.0,
  },
];

export const ScoreHonestyInspectionCard: React.FC = () => {
  const [candidates] = useState<CandidateEvaluationItemDTO[]>(defaultCandidates);
  const [rawThreshold, setRawThreshold] = useState<number>(0.5);
  const [rankingThreshold, setRankingThreshold] = useState<number>(0.5);
  const [strictMode, setStrictMode] = useState<boolean>(true);
  const [evaluated, setEvaluated] = useState<HonestCandidateResponseDTO[]>([]);
  const [stats, setStats] = useState<ScoreHonestyStatsDTO | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const runEvaluation = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const resp = await scoreHonestyService.evaluateCandidates({
        candidates,
        config: {
          raw_similarity_threshold: rawThreshold,
          ranking_score_threshold: rankingThreshold,
          strict_mode: strictMode,
        },
      });
      setEvaluated(resp.evaluated);
      setStats(resp.stats);
    } catch {
      // Offline fallback: client-side simulation
      const evaluatedSim: HonestCandidateResponseDTO[] = candidates.map((c) => {
        const raw = c.raw_similarity;
        const base = raw * (c.recency_factor ?? 1.0) * (c.importance_boost ?? 1.0);
        const rrfAdd = (c.rrf_score ?? 0.0) * 5.0;
        const mmrSub = (c.mmr_penalty ?? 0.0) * 0.25;
        const ranking = Math.min(1.0, Math.max(0.0, base * 0.85 + rrfAdd - mmrSub));
        const passedRaw = raw >= rawThreshold;
        const passedRanking = ranking >= rankingThreshold;
        const admitted = strictMode ? passedRaw && passedRanking : passedRaw || passedRanking;
        const stage = !passedRaw && !passedRanking
          ? 'both_below_threshold'
          : !passedRaw
          ? 'raw_below_threshold'
          : !passedRanking
          ? 'ranking_below_threshold'
          : 'none';

        return {
          id: c.id,
          content: c.content,
          raw_similarity: raw,
          ranking_score: ranking,
          breakdown: {
            raw_similarity: raw,
            recency_factor: c.recency_factor ?? 1.0,
            importance_boost: c.importance_boost ?? 1.0,
            mmr_penalty: c.mmr_penalty ?? 0.0,
            rrf_score: c.rrf_score ?? 0.0,
            final_ranking_score: ranking,
            explanation: `Simulated: raw=${raw.toFixed(2)}, ranking=${ranking.toFixed(2)}`,
          },
          metadata: {},
          verdict: {
            passed_raw: passedRaw,
            passed_ranking: passedRanking,
            admitted,
            rejection_stage: stage,
            rejection_reason: admitted ? null : `Filtered at ${stage}`,
          },
        };
      });

      evaluatedSim.sort((a, b) => b.ranking_score - a.ranking_score);
      const admittedCount = evaluatedSim.filter((x) => x.verdict?.admitted).length;
      const divergenceCount = evaluatedSim.filter(
        (x) => x.verdict && x.verdict.passed_raw !== x.verdict.passed_ranking
      ).length;

      setEvaluated(evaluatedSim);
      setStats({
        total_candidates: evaluatedSim.length,
        admitted_count: admittedCount,
        rejected_count: evaluatedSim.length - admittedCount,
        raw_admitted_count: evaluatedSim.filter((x) => x.verdict?.passed_raw).length,
        ranking_admitted_count: evaluatedSim.filter((x) => x.verdict?.passed_ranking).length,
        both_passed_count: evaluatedSim.filter((x) => x.verdict?.passed_raw && x.verdict?.passed_ranking).length,
        divergence_count: divergenceCount,
        divergence_rate: divergenceCount / evaluatedSim.length,
        mean_raw_similarity: 0.52,
        mean_ranking_score: 0.48,
      });
    } finally {
      setIsLoading(false);
    }
  }, [candidates, rawThreshold, rankingThreshold, strictMode]);

  useEffect(() => {
    void runEvaluation();
  }, [runEvaluation]);

  return (
    <div className="bg-card border border-border rounded-xl p-5 shadow-sm space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-primary/10 text-primary rounded-lg">
            <Scale className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground text-base">
              检索评分诚实性检验看板
            </h3>
            <p className="text-xs text-muted-foreground">
              Raw 物理相似度与复合 Ranking 分独立拆分 · 双门禁防阈值腐烂与虚高
            </p>
          </div>
        </div>
        <button
          onClick={() => void runEvaluation()}
          disabled={isLoading}
          aria-label="刷新评分检验"
          className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Threshold Controls */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 p-3 bg-muted/40 rounded-lg text-xs">
        <div>
          <div className="flex justify-between mb-1">
            <span className="font-medium text-foreground">Raw 向量门禁地板</span>
            <span className="text-primary font-mono">{rawThreshold.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={rawThreshold}
            onChange={(e) => setRawThreshold(parseFloat(e.target.value))}
            aria-label="Raw 向量相似度阈值"
            className="w-full accent-primary"
          />
        </div>
        <div>
          <div className="flex justify-between mb-1">
            <span className="font-medium text-foreground">Ranking 复合门禁地板</span>
            <span className="text-primary font-mono">{rankingThreshold.toFixed(2)}</span>
          </div>
          <input
            type="range"
            min="0"
            max="1"
            step="0.05"
            value={rankingThreshold}
            onChange={(e) => setRankingThreshold(parseFloat(e.target.value))}
            aria-label="Ranking 综合排序分阈值"
            className="w-full accent-primary"
          />
        </div>
        <div className="flex items-center justify-between md:justify-center md:space-x-4">
          <span className="font-medium text-foreground">双门禁严格模式</span>
          <button
            type="button"
            role="switch"
            aria-label="双门禁严格模式开关"
            aria-checked={strictMode}
            onClick={() => setStrictMode(!strictMode)}
            className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none ${
              strictMode ? 'bg-primary' : 'bg-muted-foreground/30'
            }`}
          >
            <span
              className={`inline-block h-3.5 w-3.5 transform rounded-full bg-background transition-transform ${
                strictMode ? 'translate-x-4.5' : 'translate-x-0.5'
              }`}
            />
          </button>
        </div>
      </div>

      {/* HUD Stats */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="p-3 bg-muted/20 border border-border/50 rounded-lg text-center">
            <div className="text-xs text-muted-foreground">总评估样本</div>
            <div className="text-lg font-semibold text-foreground font-mono mt-0.5">
              {stats.total_candidates}
            </div>
          </div>
          <div className="p-3 bg-muted/20 border border-border/50 rounded-lg text-center">
            <div className="text-xs text-muted-foreground">最终准入采纳</div>
            <div className="text-lg font-semibold text-emerald-500 font-mono mt-0.5">
              {stats.admitted_count} / {stats.total_candidates}
            </div>
          </div>
          <div className="p-3 bg-muted/20 border border-border/50 rounded-lg text-center">
            <div className="text-xs text-muted-foreground">双门禁分歧数</div>
            <div className="text-lg font-semibold text-amber-500 font-mono mt-0.5">
              {stats.divergence_count}
            </div>
          </div>
          <div className="p-3 bg-muted/20 border border-border/50 rounded-lg text-center">
            <div className="text-xs text-muted-foreground">分歧漂移率</div>
            <div className="text-lg font-semibold text-indigo-500 font-mono mt-0.5">
              {(stats.divergence_rate * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}

      {/* Candidate Comparison List */}
      <div className="space-y-3">
        <div className="text-xs font-semibold text-muted-foreground uppercase tracking-wider flex items-center space-x-1">
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>候选记忆评分诚实性分解对比</span>
        </div>

        {evaluated.map((cand) => {
          const isExpanded = expandedId === cand.id;
          const isAdmitted = cand.verdict?.admitted ?? false;
          const isDivergent =
            cand.verdict && cand.verdict.passed_raw !== cand.verdict.passed_ranking;

          return (
            <div
              key={cand.id}
              className="border border-border/70 rounded-lg p-3 bg-background/50 hover:border-primary/40 transition-colors space-y-2.5"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1 flex-1">
                  <div className="flex items-center space-x-2">
                    <span className="font-mono text-xs font-semibold text-foreground">
                      {cand.id}
                    </span>
                    {isAdmitted ? (
                      <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 text-[10px] font-medium bg-emerald-500/10 text-emerald-500 rounded border border-emerald-500/20">
                        <ShieldCheck className="w-3 h-3" />
                        <span>准入采纳</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 text-[10px] font-medium bg-rose-500/10 text-rose-500 rounded border border-rose-500/20">
                        <ShieldAlert className="w-3 h-3" />
                        <span>拒绝: {cand.verdict?.rejection_stage}</span>
                      </span>
                    )}
                    {isDivergent && (
                      <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 text-[10px] font-medium bg-amber-500/10 text-amber-500 rounded border border-amber-500/20">
                        <Info className="w-3 h-3" />
                        <span>Raw/Ranking 分歧</span>
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-foreground/90">{cand.content}</p>
                </div>

                <button
                  onClick={() => setExpandedId(isExpanded ? null : cand.id)}
                  aria-label={`展开 ${cand.id} 评分因子`}
                  className="p-1 text-muted-foreground hover:text-foreground rounded transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
                >
                  {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                </button>
              </div>

              {/* Progress bars comparison */}
              <div className="grid grid-cols-2 gap-4 text-xs pt-1">
                <div>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-muted-foreground">Raw 向量相似度</span>
                    <span className="font-mono font-medium text-foreground">
                      {(cand.raw_similarity * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        cand.verdict?.passed_raw ? 'bg-sky-500' : 'bg-rose-500/70'
                      }`}
                      style={{ width: `${cand.raw_similarity * 100}%` }}
                    />
                  </div>
                </div>

                <div>
                  <div className="flex justify-between text-[11px] mb-1">
                    <span className="text-muted-foreground">Ranking 复合排序分</span>
                    <span className="font-mono font-medium text-foreground">
                      {(cand.ranking_score * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
                    <div
                      className={`h-full ${
                        cand.verdict?.passed_ranking ? 'bg-indigo-500' : 'bg-rose-500/70'
                      }`}
                      style={{ width: `${cand.ranking_score * 100}%` }}
                    />
                  </div>
                </div>
              </div>

              {/* Expanded Breakdown */}
              {isExpanded && cand.breakdown && (
                <div className="mt-2 p-2.5 bg-muted/30 rounded border border-border/50 text-[11px] space-y-1.5">
                  <div className="font-medium text-foreground">白盒归因因子明细：</div>
                  <div className="grid grid-cols-3 gap-2 font-mono text-muted-foreground">
                    <div>Recency: ×{cand.breakdown.recency_factor.toFixed(2)}</div>
                    <div>Importance: ×{cand.breakdown.importance_boost.toFixed(2)}</div>
                    <div>MMR 惩罚: -{cand.breakdown.mmr_penalty.toFixed(2)}</div>
                    <div>RRF 分: +{cand.breakdown.rrf_score.toFixed(3)}</div>
                  </div>
                  <div className="text-xs text-foreground/80 font-mono pt-1">
                    公式解释: {cand.breakdown.explanation}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
