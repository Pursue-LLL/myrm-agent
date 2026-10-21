/**
 * [INPUT]
 * Props: conflicts, reconciliationResults, onReconcile, reconciling
 *
 * [OUTPUT]
 * DialecticReconciliationConsoleView: Layer 2 Multi-Pass Dialectic Reasoning & Contradiction Resolution Console.
 *
 * [POS]
 * Sub-view in TwoLayerDialecticStudioCard for Item 112.
 * Strict typing applied: No `any` types allowed. Accessible markup. Single file < 350 lines.
 */

import React, { useState } from 'react';
import {
  Sparkles,
  GitCompare,
  ArrowRight,
  ShieldCheck,
  CheckCircle,
  FileCheck,
  Zap,
} from 'lucide-react';
import type {
  DialecticConflictCandidateDTO,
  DialecticReconciliationResultDTO,
} from '@/services/memory/twoLayerDialectic';

export interface DialecticReconciliationConsoleViewProps {
  conflicts: DialecticConflictCandidateDTO[];
  reconciliationResults: DialecticReconciliationResultDTO[];
  onReconcile: (statements: string[], depth: number) => Promise<void>;
  reconciling: boolean;
}

export const DialecticReconciliationConsoleView: React.FC<
  DialecticReconciliationConsoleViewProps
> = ({ conflicts, reconciliationResults, onReconcile, reconciling }) => {
  const [selectedDepth, setSelectedDepth] = useState<number>(3);
  const [customStatementA, setCustomStatementA] = useState<string>(
    '存储层采用 PostgreSQL 作为集群关系型数据源。',
  );
  const [customStatementB, setCustomStatementB] = useState<string>(
    '存储层切换至 SQLite 嵌入式引擎以支持本地离线自包含运行。',
  );

  const handleRunReconcile = async () => {
    if (!customStatementA.trim() || !customStatementB.trim()) {
      return;
    }
    await onReconcile([customStatementA.trim(), customStatementB.trim()], selectedDepth);
  };

  const handleSelectPreset = (c: DialecticConflictCandidateDTO) => {
    setCustomStatementA(c.statement_a);
    setCustomStatementB(c.statement_b);
  };

  return (
    <div className="space-y-4">
      {/* 头部原理说明 */}
      <div className="p-3.5 rounded-lg bg-purple-500/10 border border-purple-500/20 space-y-1.5">
        <div className="flex items-center gap-2 text-xs font-semibold text-purple-700 dark:text-purple-400">
          <Sparkles className="w-4 h-4 shrink-0" />
          <span>Layer 2 自适应多遍辩证推理 (Pass 0 审查 → Pass 1 综合 → Pass 2 调和)</span>
        </div>
        <p className="text-xs text-purple-800 dark:text-purple-300/90 leading-relaxed">
          当检测到跨会话多条互相冲突的记忆或历史决策矛盾时，不污染静态底座，而是触发 1~3 遍自适应辩证推理循环，在推理层自愈冲突并产出权威决议。
        </p>
      </div>

      {/* 调和工作区：左侧测试触发器，右侧冲突库 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：冲突调和演练台 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3.5">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span className="flex items-center gap-1.5">
              <GitCompare className="w-3.5 h-3.5 text-primary" />
              <span>辩证矛盾调和演练台</span>
            </span>
            <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
              <label htmlFor="dialectic-depth-select" className="font-medium">
                推理深度:
              </label>
              <select
                id="dialectic-depth-select"
                value={selectedDepth}
                onChange={(e) => setSelectedDepth(Number(e.target.value))}
                className="px-2 py-0.5 rounded text-xs bg-background border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground"
              >
                <option value={1}>Pass 1 (轻量审查)</option>
                <option value={2}>Pass 2 (标准综合)</option>
                <option value={3}>Pass 3 (深度调和)</option>
              </select>
            </div>
          </div>

          <div className="space-y-2.5">
            <div className="space-y-1">
              <label
                htmlFor="dialectic-statement-a-input"
                className="text-[11px] font-medium text-muted-foreground block"
              >
                历史前序断言 (Statement A)
              </label>
              <textarea
                id="dialectic-statement-a-input"
                value={customStatementA}
                onChange={(e) => setCustomStatementA(e.target.value)}
                rows={2}
                className="w-full p-2 text-xs bg-background rounded-md border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground resize-none"
              />
            </div>

            <div className="space-y-1">
              <label
                htmlFor="dialectic-statement-b-input"
                className="text-[11px] font-medium text-muted-foreground block"
              >
                当前竞争/最新断言 (Statement B)
              </label>
              <textarea
                id="dialectic-statement-b-input"
                value={customStatementB}
                onChange={(e) => setCustomStatementB(e.target.value)}
                rows={2}
                className="w-full p-2 text-xs bg-background rounded-md border border-input focus:outline-none focus:ring-2 focus:ring-primary text-foreground resize-none"
              />
            </div>

            <div className="flex justify-end pt-1">
              <button
                type="button"
                aria-label="执行多遍辩证推理调和"
                onClick={handleRunReconcile}
                disabled={reconciling || !customStatementA.trim() || !customStatementB.trim()}
                className="flex items-center gap-1.5 px-4 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 transition-colors focus:outline-none focus:ring-2 focus:ring-primary disabled:opacity-50"
              >
                <Zap className={`w-3.5 h-3.5 ${reconciling ? 'animate-spin' : ''}`} />
                <span>{reconciling ? '推理调和中...' : `执行 Pass ${selectedDepth} 辩证消解`}</span>
              </button>
            </div>
          </div>
        </div>

        {/* 右侧：典型矛盾冲突候选库 */}
        <div className="p-4 bg-card/60 rounded-lg border border-border space-y-3">
          <div className="text-xs font-semibold text-foreground flex items-center justify-between">
            <span>典型认知冲突候选库 ({conflicts.length})</span>
            <span className="text-[10px] text-muted-foreground">点击快速载入演练台</span>
          </div>

          <div className="space-y-2">
            {conflicts.map((c, idx) => (
              <button
                key={`conflict-candidate-${idx}`}
                type="button"
                aria-label={`载入预设认知冲突: ${c.subject_domain}`}
                onClick={() => handleSelectPreset(c)}
                className="w-full text-left p-2.5 rounded-md bg-muted/30 border border-border/80 hover:border-primary/50 transition-all focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-[11px] font-medium text-primary">
                    {c.subject_domain}
                  </span>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/10 text-purple-600 dark:text-purple-400 border border-purple-500/20 font-mono">
                    互斥度: {Math.round(c.conflict_score * 100)}%
                  </span>
                </div>
                <div className="space-y-1 text-[11px] text-muted-foreground">
                  <div className="line-clamp-1">A: {c.statement_a}</div>
                  <div className="line-clamp-1">B: {c.statement_b}</div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* 调和结果与多遍思考轨迹展示 */}
      <div className="space-y-2.5">
        <div className="text-xs font-semibold text-foreground flex items-center justify-between">
          <div className="flex items-center gap-1.5">
            <FileCheck className="w-3.5 h-3.5 text-emerald-500" />
            <span>辩证调和权威指令与多遍思考轨迹</span>
          </div>
          <span className="text-[11px] text-muted-foreground">消除二义性决策</span>
        </div>

        {reconciliationResults.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground bg-muted/20 rounded-lg border border-dashed border-border">
            暂无调和结果，请点击上方按钮发起辩证推理
          </div>
        ) : (
          <div className="space-y-3">
            {reconciliationResults.map((res, idx) => (
              <div
                key={`rec-result-${idx}`}
                className="p-4 rounded-lg bg-card/70 border border-border space-y-3"
              >
                {/* 最终决议 */}
                <div className="flex items-start justify-between gap-3">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 text-emerald-500 shrink-0" />
                      <span className="text-xs font-semibold text-foreground">
                        权威调和决议 (Resolved Statement)
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20">
                        置信度 {Math.round(res.confidence * 100)}%
                      </span>
                    </div>
                    <p className="text-xs text-foreground bg-muted/30 p-2.5 rounded-md leading-relaxed">
                      {res.resolved_statement}
                    </p>
                  </div>
                </div>

                {/* 被取代的过时断言 */}
                {res.superseded_statements.length > 0 && (
                  <div className="text-[11px] text-muted-foreground flex items-center gap-1.5">
                    <span className="font-medium text-foreground">被取代过时断言:</span>
                    <span className="line-through">
                      {res.superseded_statements.join('; ')}
                    </span>
                  </div>
                )}

                {/* 辩证推理轨迹 */}
                {res.rationale && (
                  <div className="p-2.5 rounded bg-muted/20 border border-border/60 text-[11px] text-muted-foreground leading-relaxed">
                    <span className="font-medium text-foreground">辩证思考轨迹 (Rationale): </span>
                    {res.rationale}
                  </div>
                )}

                {/* 执行的 Passes 药丸 */}
                <div className="flex flex-wrap items-center gap-1.5 pt-1">
                  <span className="text-[10px] text-muted-foreground">已执行阶段:</span>
                  {res.passes_executed.map((passName, pIdx) => (
                    <span
                      key={`pass-pill-${pIdx}`}
                      className="px-2 py-0.5 rounded text-[10px] font-mono bg-primary/10 text-primary border border-primary/20"
                    >
                      {passName}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
