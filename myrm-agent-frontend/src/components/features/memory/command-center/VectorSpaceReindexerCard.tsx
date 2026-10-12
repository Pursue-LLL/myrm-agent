/**
 * [INPUT]
 * @/services/memory/vectorSpaceGuard::SpaceFingerprintDTO, SpaceReindexResponse, VectorMetricType
 * ./vectorSpaceGuardFallbacks::PRESET_MODEL_FINGERPRINTS
 * lucide-react::RefreshCw, CheckCircle2, AlertOctagon, ArrowUpRight, Database
 *
 * [OUTPUT]
 * Component: VectorSpaceReindexerCard
 *
 * [POS]
 * Pipeline control card for executing guarded vector space migration and re-indexing.
 * Ensures zero semantic pollution when transitioning vector spaces.
 * Strictly typed with zero `any`. Single file < 250 lines.
 */

import React, { useState } from 'react';
import {
  RefreshCw,
  CheckCircle2,
  AlertOctagon,
  ArrowUpRight,
  Database,
} from 'lucide-react';
import type {
  SpaceFingerprintDTO,
  SpaceReindexResponse,
  VectorMetricType,
} from '@/services/memory/vectorSpaceGuard';
import { PRESET_MODEL_FINGERPRINTS } from './vectorSpaceGuardFallbacks';

interface VectorSpaceReindexerCardProps {
  collection: string;
  onReindex: (
    collection: string,
    targetFp: SpaceFingerprintDTO,
    sampleItems: string[]
  ) => Promise<void>;
  reindexResult: SpaceReindexResponse | null;
  isReindexing: boolean;
}

export const VectorSpaceReindexerCard: React.FC<
  VectorSpaceReindexerCardProps
> = ({
  collection,
  onReindex,
  reindexResult,
  isReindexing,
}) => {
  const [targetPreset, setTargetPreset] = useState<string>('ollama-bge');
  const [providerId, setProviderId] = useState<string>('ollama');
  const [modelName, setModelName] = useState<string>('bge-m3');
  const [dimension, setDimension] = useState<number>(1024);
  const [metricType, setMetricType] = useState<VectorMetricType>('cosine');

  const handlePresetSelect = (key: string) => {
    setTargetPreset(key);
    const preset = PRESET_MODEL_FINGERPRINTS[key];
    if (preset) {
      setProviderId(preset.provider_id);
      setModelName(preset.model_name);
      setDimension(preset.vector_dimension);
      setMetricType(preset.metric_type);
    }
  };

  const handleTriggerReindex = () => {
    const targetFp: SpaceFingerprintDTO = {
      provider_id: providerId,
      model_name: modelName,
      vector_dimension: dimension,
      metric_type: metricType,
    };
    void onReindex(collection, targetFp, []);
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-4">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div>
          <h4 className="font-medium text-foreground text-sm flex items-center gap-2">
            <Database className="w-4 h-4 text-primary" aria-hidden="true" />
            <span>空间迁移与向量重索引流水线</span>
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            当更换基底 Embedding 模型或升级向量维度时，触发原子化全量重新嵌入与指纹更新
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <div>
            <label
              htmlFor="reindex-target-preset"
              className="block text-xs font-medium text-foreground mb-1"
            >
              目标基底模型预设
            </label>
            <select
              id="reindex-target-preset"
              value={targetPreset}
              onChange={(e) => handlePresetSelect(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="ollama-bge">Ollama bge-m3 (1024d, Cosine)</option>
              <option value="openai-large">OpenAI text-embedding-3-large (3072d, Cosine)</option>
              <option value="openai-small">OpenAI text-embedding-3-small (1536d, Cosine)</option>
              <option value="voyage-3">Voyage voyage-3 (1024d, Cosine)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label
                htmlFor="reindex-input-provider"
                className="block text-xs font-medium text-foreground mb-1"
              >
                目标提供商
              </label>
              <input
                id="reindex-input-provider"
                type="text"
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label
                htmlFor="reindex-input-model"
                className="block text-xs font-medium text-foreground mb-1"
              >
                目标模型名称
              </label>
              <input
                id="reindex-input-model"
                type="text"
                value={modelName}
                onChange={(e) => setModelName(e.target.value)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label
                htmlFor="reindex-input-dim"
                className="block text-xs font-medium text-foreground mb-1"
              >
                目标维度
              </label>
              <input
                id="reindex-input-dim"
                type="number"
                min={1}
                value={dimension}
                onChange={(e) => setDimension(parseInt(e.target.value, 10) || 1)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label
                htmlFor="reindex-select-metric"
                className="block text-xs font-medium text-foreground mb-1"
              >
                度量方式
              </label>
              <select
                id="reindex-select-metric"
                value={metricType}
                onChange={(e) => setMetricType(e.target.value as VectorMetricType)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <option value="cosine">余弦相似度 (Cosine)</option>
                <option value="dot">点积 (Dot)</option>
                <option value="euclidean">欧氏距离 (Euclidean)</option>
              </select>
            </div>
          </div>

          <div className="pt-2">
            <button
              type="button"
              onClick={handleTriggerReindex}
              disabled={isReindexing || !collection.trim()}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium rounded-lg bg-secondary text-secondary-foreground hover:bg-secondary/80 border border-border transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isReindexing ? 'animate-spin' : ''}`}
                aria-hidden="true"
              />
              <span>{isReindexing ? '正在执行重索引迁移...' : '启动安全空间迁移'}</span>
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/50">
              <span className="text-xs font-medium text-foreground">流水线执行状态</span>
              {reindexResult && (
                <span
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    reindexResult.status === 'completed'
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : reindexResult.status === 'failed'
                        ? 'bg-destructive/10 text-destructive'
                        : 'bg-primary/10 text-primary'
                  }`}
                >
                  {reindexResult.status === 'completed'
                    ? '已完成'
                    : reindexResult.status === 'failed'
                      ? '执行失败'
                      : '处理中'}
                </span>
              )}
            </div>

            {reindexResult ? (
              <div className="space-y-2 text-xs">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">目标集合:</span>
                  <span className="font-mono text-foreground font-medium">
                    {reindexResult.collection}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">重新嵌入向量数:</span>
                  <span className="font-mono text-foreground font-semibold">
                    {reindexResult.reindexed_count}
                  </span>
                </div>
                {reindexResult.error_message && (
                  <div className="p-2 rounded bg-destructive/10 border border-destructive/20 text-destructive text-xs">
                    {reindexResult.error_message}
                  </div>
                )}
                {reindexResult.status === 'completed' && (
                  <div className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 pt-2">
                    <CheckCircle2 className="w-4 h-4 shrink-0" aria-hidden="true" />
                    <span>集合向量空间与新基底模型指纹已成功同步！</span>
                  </div>
                )}
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground space-y-2">
                <ArrowUpRight className="w-8 h-8 mx-auto text-muted-foreground/40" aria-hidden="true" />
                <p>配置目标模型基底后，可一键执行受守卫保护的安全迁移</p>
              </div>
            )}
          </div>

          <div className="mt-3 pt-2 border-t border-border/50 text-[11px] text-muted-foreground flex items-center gap-1">
            <AlertOctagon className="w-3.5 h-3.5 text-amber-500 shrink-0" aria-hidden="true" />
            <span>迁移过程会自动清空旧基底向量并更新空间元数据</span>
          </div>
        </div>
      </div>
    </div>
  );
};
