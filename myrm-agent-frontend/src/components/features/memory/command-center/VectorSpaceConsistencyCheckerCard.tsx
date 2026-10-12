/**
 * [INPUT]
 * @/services/memory/vectorSpaceGuard::SpaceFingerprintDTO, SpaceValidateResponse, VectorMetricType
 * ./vectorSpaceGuardFallbacks::PRESET_MODEL_FINGERPRINTS
 * lucide-react::CheckCircle2, AlertTriangle, XCircle, ArrowRightLeft, ShieldAlert
 *
 * [OUTPUT]
 * Component: VectorSpaceConsistencyCheckerCard
 *
 * [POS]
 * Interactive pre-flight vector space consistency validator card.
 * Verifies embedding model dimension and base compatibility before writes or searches.
 * Strictly typed with zero `any`. Full a11y compliance. Single file < 350 lines.
 */

import React, { useState } from 'react';
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  ArrowRightLeft,
  ShieldAlert,
} from 'lucide-react';
import type {
  SpaceFingerprintDTO,
  SpaceValidateResponse,
  VectorMetricType,
} from '@/services/memory/vectorSpaceGuard';
import { PRESET_MODEL_FINGERPRINTS } from './vectorSpaceGuardFallbacks';

interface VectorSpaceConsistencyCheckerCardProps {
  collection: string;
  onValidate: (
    collection: string,
    fp: SpaceFingerprintDTO,
    autoBind: boolean
  ) => Promise<void>;
  onBind: (collection: string, fp: SpaceFingerprintDTO) => Promise<void>;
  validateResult: SpaceValidateResponse | null;
  isValidating: boolean;
  isBinding: boolean;
}

export const VectorSpaceConsistencyCheckerCard: React.FC<
  VectorSpaceConsistencyCheckerCardProps
> = ({
  collection,
  onValidate,
  onBind,
  validateResult,
  isValidating,
  isBinding,
}) => {
  const [selectedPreset, setSelectedPreset] = useState<string>('openai-small');
  const [providerId, setProviderId] = useState<string>('openai');
  const [modelName, setModelName] = useState<string>('text-embedding-3-small');
  const [dimension, setDimension] = useState<number>(1536);
  const [metricType, setMetricType] = useState<VectorMetricType>('cosine');
  const [autoBind, setAutoBind] = useState<boolean>(false);

  const handlePresetChange = (presetKey: string) => {
    setSelectedPreset(presetKey);
    const preset = PRESET_MODEL_FINGERPRINTS[presetKey];
    if (preset) {
      setProviderId(preset.provider_id);
      setModelName(preset.model_name);
      setDimension(preset.vector_dimension);
      setMetricType(preset.metric_type);
    }
  };

  const currentFp: SpaceFingerprintDTO = {
    provider_id: providerId,
    model_name: modelName,
    vector_dimension: dimension,
    metric_type: metricType,
  };

  const handleValidateClick = () => {
    void onValidate(collection, currentFp, autoBind);
  };

  const handleBindClick = () => {
    void onBind(collection, currentFp);
  };

  return (
    <div className="rounded-xl border border-border bg-card p-5 shadow-sm space-y-5">
      <div className="flex items-center justify-between pb-3 border-b border-border">
        <div>
          <h4 className="font-medium text-foreground text-sm">
            运行时模型指纹与预检校验
          </h4>
          <p className="text-xs text-muted-foreground mt-0.5">
            在进行向量写入或检索前，校验当前 Embedding 模型基底与集合的兼容性
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="space-y-3">
          <div>
            <label
              htmlFor="model-preset-select"
              className="block text-xs font-medium text-foreground mb-1"
            >
              快速预设配置
            </label>
            <select
              id="model-preset-select"
              value={selectedPreset}
              onChange={(e) => handlePresetChange(e.target.value)}
              className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <option value="openai-small">OpenAI text-embedding-3-small (1536d, Cosine)</option>
              <option value="openai-large">OpenAI text-embedding-3-large (3072d, Cosine)</option>
              <option value="ollama-bge">Ollama bge-m3 (1024d, Cosine)</option>
              <option value="voyage-3">Voyage voyage-3 (1024d, Cosine)</option>
            </select>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label
                htmlFor="input-provider-id"
                className="block text-xs font-medium text-foreground mb-1"
              >
                提供商 ID
              </label>
              <input
                id="input-provider-id"
                type="text"
                value={providerId}
                onChange={(e) => setProviderId(e.target.value)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label
                htmlFor="input-model-name"
                className="block text-xs font-medium text-foreground mb-1"
              >
                模型名称
              </label>
              <input
                id="input-model-name"
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
                htmlFor="input-dimension"
                className="block text-xs font-medium text-foreground mb-1"
              >
                坐标维度 (Dimensions)
              </label>
              <input
                id="input-dimension"
                type="number"
                min={1}
                value={dimension}
                onChange={(e) => setDimension(parseInt(e.target.value, 10) || 1)}
                className="w-full px-3 py-1.5 text-xs rounded-lg border border-border bg-background text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <label
                htmlFor="select-metric-type"
                className="block text-xs font-medium text-foreground mb-1"
              >
                度量方式 (Metric)
              </label>
              <select
                id="select-metric-type"
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

          <div className="flex items-center gap-2 pt-1">
            <input
              id="checkbox-auto-bind"
              type="checkbox"
              checked={autoBind}
              onChange={(e) => setAutoBind(e.target.checked)}
              className="w-4 h-4 rounded border-border text-primary focus:ring-2 focus:ring-primary"
            />
            <label
              htmlFor="checkbox-auto-bind"
              className="text-xs text-muted-foreground select-none cursor-pointer"
            >
              若集合未初始化，则自动绑定此指纹
            </label>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <button
              type="button"
              onClick={handleValidateClick}
              disabled={isValidating || !collection.trim()}
              className="flex-1 px-3 py-2 text-xs font-medium rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {isValidating ? '正在校验...' : '执行预检校验'}
            </button>
            <button
              type="button"
              onClick={handleBindClick}
              disabled={isBinding || !collection.trim()}
              className="px-3 py-2 text-xs font-medium rounded-lg border border-border bg-background hover:bg-muted text-foreground transition-colors disabled:opacity-50 focus:outline-none focus:ring-2 focus:ring-primary"
            >
              {isBinding ? '绑定中...' : '绑定指纹'}
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-border bg-muted/30 p-4 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between pb-2 mb-2 border-b border-border/50">
              <span className="text-xs font-medium text-foreground">校验诊断结果</span>
              {validateResult && (
                <span
                  className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full font-medium ${
                    validateResult.is_valid
                      ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400'
                      : 'bg-destructive/10 text-destructive'
                  }`}
                >
                  {validateResult.is_valid ? (
                    <>
                      <CheckCircle2 className="w-3 h-3" aria-hidden="true" />
                      <span>通过 (Consistent)</span>
                    </>
                  ) : (
                    <>
                      <XCircle className="w-3 h-3" aria-hidden="true" />
                      <span>异常 ({validateResult.status})</span>
                    </>
                  )}
                </span>
              )}
            </div>

            {validateResult ? (
              <div className="space-y-3">
                <p className="text-xs text-foreground bg-background p-2.5 rounded border border-border">
                  {validateResult.message}
                </p>

                <div className="text-xs space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="text-muted-foreground">推荐处理策略:</span>
                    <span className="font-mono font-medium text-foreground">
                      {validateResult.recommended_action}
                    </span>
                  </div>
                  {validateResult.expected_fingerprint && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">空间期望模型:</span>
                      <span className="font-mono text-foreground">
                        {validateResult.expected_fingerprint.provider_id}/
                        {validateResult.expected_fingerprint.model_name} (
                        {validateResult.expected_fingerprint.vector_dimension}d)
                      </span>
                    </div>
                  )}
                  {validateResult.current_fingerprint && (
                    <div className="flex items-center justify-between">
                      <span className="text-muted-foreground">当前运行模型:</span>
                      <span className="font-mono text-foreground">
                        {validateResult.current_fingerprint.provider_id}/
                        {validateResult.current_fingerprint.model_name} (
                        {validateResult.current_fingerprint.vector_dimension}d)
                      </span>
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="py-8 text-center text-xs text-muted-foreground space-y-2">
                <ArrowRightLeft className="w-8 h-8 mx-auto text-muted-foreground/40" aria-hidden="true" />
                <p>点击“执行预检校验”以测试当前模型与集合向量空间的对齐情况</p>
              </div>
            )}
          </div>

          <div className="mt-3 pt-2 border-t border-border/50 text-[11px] text-muted-foreground flex items-center gap-1">
            <ShieldAlert className="w-3.5 h-3.5 text-primary shrink-0" aria-hidden="true" />
            <span>杜绝不同 Embedding 模型或不同维度混用导致的向量基底语义污染</span>
          </div>
        </div>
      </div>
    </div>
  );
};
