'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import {
  Cpu,
  HardDrive,
  Monitor,
  AlertTriangle,
  Download,
  Loader2,
  X,
  Trash2,
  Sliders,
  Layers,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import { Alert, AlertDescription, AlertTitle } from '@/components/primitives/alert';
import { getDeployMode } from '@/lib/deploy-mode';
import { HARDWARE_RUNGS, getRungByVram } from '@/lib/utils/hardwareSimulator';

interface HardwareRecommendation {
  model_id: string;
  name: string;
  description: string;
  req_vram_gb: number;
  params_b: number;
  disk_size_gb?: number;
  min_rung?: number;
  num_layers?: number;
  kv_heads?: number;
  head_dim?: number;
  kv_fp16_64k_gb?: number;
  kv_q8_64k_gb?: number;
  kv_q4_64k_gb?: number;
  total_vram_64k_fp16_gb?: number;
  total_vram_64k_q8_gb?: number;
  fit_score: number;
  fit_level: 'perfect' | 'good' | 'fair' | 'poor';
  is_installed?: boolean;
  est_tok_per_sec?: number | null;
}

interface HardwareProfile {
  hardware_detected: boolean;
  os_type?: string;
  cpu_arch?: string;
  total_ram_gb?: number;
  free_disk_gb?: number;
  has_gpu?: boolean;
  gpu_name?: string;
  gpu_vram_gb?: number;
  is_unified_memory?: boolean;
  available_vram_gb?: number;
  current_rung?: number;
  rung_name?: string;
  ollama_running?: boolean;
  recommendations: HardwareRecommendation[];
}

interface HardwareCookbookProps {
  onApplyModel: (modelId: string) => void;
}

export default function HardwareCookbook({ onApplyModel }: HardwareCookbookProps) {
  const t = useTranslations('settings.modelService.cookbook');
  const [profile, setProfile] = useState<HardwareProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 跨机硬件模拟器状态
  const [isSimulatorOpen, setIsSimulatorOpen] = useState(false);
  const [simulatedVram, setSimulatedVram] = useState<number>(16);

  const [downloadingModel, setDownloadingModel] = useState<string | null>(null);
  const [downloadProgress, setDownloadProgress] = useState<{
    status: string;
    completed?: number;
    total?: number;
  } | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const [deletingModel, setDeletingModel] = useState<string | null>(null);

  // SaaS 模式下直接隐藏
  const isSaaS = getDeployMode() === 'sandbox';

  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const fetchHardwareProfile = async () => {
    try {
      const res = await fetch('/api/v1/integrations/hardware/recommendations');
      if (!res.ok) {
        throw new Error('Failed to fetch hardware recommendations');
      }
      const data = await res.json();
      if (data.code === 0 && data.data) {
        setProfile(data.data);
        if (data.data.available_vram_gb) {
          setSimulatedVram(data.data.available_vram_gb);
        }
      } else {
        throw new Error(data.message || 'Unknown error');
      }
    } catch (err) {
      console.error('Hardware detection failed:', err);
      setError(err instanceof Error ? err.message : 'Failed to detect hardware');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isSaaS) {
      setLoading(false);
      return;
    }
    fetchHardwareProfile();
  }, [isSaaS]);

  const handleDownload = async (modelId: string) => {
    const ollamaModelName = modelId.includes('/') ? modelId.split('/')[1] : modelId;

    setDownloadingModel(modelId);
    setDownloadProgress({ status: t('downloading') });

    abortControllerRef.current = new AbortController();

    try {
      const res = await fetch('/api/v1/integrations/hardware/ollama/pull', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: ollamaModelName }),
        signal: abortControllerRef.current.signal,
      });

      if (!res.ok) {
        throw new Error('Failed to start download');
      }

      if (!res.body) {
        throw new Error('ReadableStream not supported in response');
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.trim()) continue;
          try {
            const data = JSON.parse(line);
            if (data.error) {
              throw new Error(data.error);
            }
            setDownloadProgress({
              status: data.status,
              completed: data.completed,
              total: data.total,
            });
          } catch (jsonErr) {
            console.error('Failed to parse NDJSON line:', line, jsonErr);
          }
        }
      }

      toast.success(t('installed'));
      await fetchHardwareProfile();
      onApplyModel(modelId);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === 'AbortError') {
        toast.info(t('cancel'));
      } else {
        console.error('Download failed:', err);
        toast.error(err instanceof Error ? err.message : 'Download failed');
      }
    } finally {
      setDownloadingModel(null);
      setDownloadProgress(null);
      abortControllerRef.current = null;
    }
  };

  const handleCancelDownload = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleDelete = async (modelId: string) => {
    const ollamaModelName = modelId.includes('/') ? modelId.split('/')[1] : modelId;

    if (!window.confirm(t('confirmDelete', { model: ollamaModelName }))) {
      return;
    }

    setDeletingModel(modelId);
    try {
      const res = await fetch('/api/v1/integrations/hardware/ollama/models', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model_name: ollamaModelName }),
      });

      if (!res.ok) {
        throw new Error('Failed to delete model');
      }

      const data = await res.json();
      if (data.code === 0 && data.data?.success) {
        toast.success(t('delete'));
        await fetchHardwareProfile();
      } else {
        throw new Error(data.message || 'Delete failed');
      }
    } catch (err) {
      console.error('Delete failed:', err);
      toast.error(t('deleteFailed'));
    } finally {
      setDeletingModel(null);
    }
  };

  const getFitLevelColor = (level: string) => {
    switch (level) {
      case 'perfect':
        return 'text-green-600 bg-green-500/10 border-green-500/20';
      case 'good':
        return 'text-emerald-600 bg-emerald-500/10 border-emerald-500/20';
      case 'fair':
        return 'text-yellow-600 bg-yellow-500/10 border-yellow-500/20';
      case 'poor':
      default:
        return 'text-red-600 bg-red-500/10 border-red-500/20';
    }
  };

  // 当前有效 VRAM（若开启模拟器则采用模拟值）
  const effectiveVram = isSimulatorOpen ? simulatedVram : profile?.available_vram_gb || 8;
  const activeRung = useMemo(() => getRungByVram(effectiveVram), [effectiveVram]);

  // 动态计算模拟显存适配后的推荐与评分
  const simulatedRecommendations = useMemo(() => {
    if (!profile?.recommendations) return [];
    return profile.recommendations.map((rec) => {
      const weightGb = rec.req_vram_gb;
      const kvFp16Gb =
        rec.kv_fp16_64k_gb ||
        calculateKvCacheVramGb(rec.num_layers || 32, rec.kv_heads || 8, rec.head_dim || 128, 65536, 2.0);
      const kvQ8Gb =
        rec.kv_q8_64k_gb ||
        calculateKvCacheVramGb(rec.num_layers || 32, rec.kv_heads || 8, rec.head_dim || 128, 65536, 1.0);
      const totalNeeded64k = rec.total_vram_64k_fp16_gb || weightGb + kvFp16Gb;
      const totalNeeded64kQ8 = rec.total_vram_64k_q8_gb || weightGb + kvQ8Gb;

      if (!isSimulatorOpen) {
        return {
          ...rec,
          effectiveFitScore: rec.fit_score,
          effectiveFitLevel: rec.fit_level,
          weightGb,
          kvFp16Gb,
          kvQ8Gb,
          totalNeeded64k,
        };
      }

      let score = 0;
      let fitLevel: 'perfect' | 'good' | 'fair' | 'poor' = 'poor';

      if (simulatedVram >= totalNeeded64k) {
        const ratio = simulatedVram / totalNeeded64k;
        if (ratio >= 1.6) {
          score = 95;
          fitLevel = 'perfect';
        } else if (ratio >= 1.2) {
          score = 88;
          fitLevel = 'good';
        } else {
          score = 78;
          fitLevel = 'good';
        }
      } else if (simulatedVram >= totalNeeded64kQ8) {
        score = 72;
        fitLevel = 'fair';
      } else if (simulatedVram >= weightGb) {
        score = 55;
        fitLevel = 'fair';
      } else {
        const ratio = simulatedVram / weightGb;
        score = Math.floor(ratio * 40);
        fitLevel = 'poor';
      }

      return {
        ...rec,
        effectiveFitScore: score,
        effectiveFitLevel: fitLevel,
        weightGb,
        kvFp16Gb,
        kvQ8Gb,
        totalNeeded64k,
      };
    });
  }, [profile?.recommendations, isSimulatorOpen, simulatedVram]);

  if (isSaaS || (!loading && !profile?.hardware_detected)) {
    return null;
  }

  if (loading) {
    return (
      <Card className="border-border/50 shadow-sm">
        <CardContent className="flex items-center justify-center p-8 text-muted-foreground gap-2">
          <Loader2 className="w-5 h-5 animate-spin text-primary" />
          <span>{t('detecting')}</span>
        </CardContent>
      </Card>
    );
  }

  if (error || !profile) {
    return null;
  }

  return (
    <Card className="border-primary/30 shadow-sm overflow-hidden">
      <div className="bg-primary/5 border-b border-primary/10 px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-lg font-semibold flex items-center gap-2">
              <Monitor className="w-5 h-5 text-primary" />
              {t('title')}
            </CardTitle>
            <CardDescription className="mt-1">{t('description')}</CardDescription>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className={`h-8 gap-1.5 text-xs ${isSimulatorOpen ? 'bg-primary/10 border-primary/30 text-primary' : ''}`}
              onClick={() => setIsSimulatorOpen(!isSimulatorOpen)}
            >
              <Sliders className="w-3.5 h-3.5" />
              {t('simulatorTitle')}
            </Button>
            <Badge variant="outline" className="bg-background/50 backdrop-blur">
              {t('localModeOnly')}
            </Badge>
          </div>
        </div>
      </div>

      <CardContent className="p-0">
        {/* 硬件信息展示 */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-6 bg-muted/30 border-b border-border/50">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <Cpu className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('cpuArch')}</div>
              <div className="font-medium text-sm">
                {profile.cpu_arch || 'Unknown'} ({profile.os_type})
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <HardDrive className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('memory')}</div>
              <div className="font-medium text-sm">
                {profile.total_ram_gb} GB {profile.is_unified_memory ? t('unified') : 'RAM'}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <Monitor className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('gpu')}</div>
              <div className="font-medium text-sm truncate max-w-[150px]" title={profile.gpu_name || t('noGpu')}>
                {profile.gpu_name || t('noGpu')}
              </div>
              {profile.available_vram_gb && (
                <div className="text-xs text-primary font-medium">
                  {t('availableVram')}: {profile.available_vram_gb} GB
                </div>
              )}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="p-2 bg-background rounded-md border shadow-sm">
              <HardDrive className="w-4 h-4 text-muted-foreground" />
            </div>
            <div>
              <div className="text-xs text-muted-foreground">{t('diskSpace')}</div>
              <div className="font-medium text-sm">
                {profile.free_disk_gb ? `${profile.free_disk_gb} GB ${t('free')}` : 'Unknown'}
              </div>
            </div>
          </div>
        </div>

        {/* 硬件阶梯图谱 (Reference Ladder) */}
        <div className="px-6 py-4 bg-muted/10 border-b border-border/50">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-primary" />
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                {t('hardwareLadder')}
              </span>
            </div>
            <div className="flex items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">{t('currentRung')}:</span>
              <Badge className="bg-primary/20 text-primary border-primary/30 text-[11px] font-semibold">
                Rung {activeRung.rung} - {activeRung.name}
              </Badge>
            </div>
          </div>

          <div className="grid grid-cols-5 gap-2">
            {HARDWARE_RUNGS.map((r) => {
              const isCurrent = r.rung === activeRung.rung;
              return (
                <div
                  key={r.rung}
                  className={`p-2.5 rounded-md border text-center transition-all ${
                    isCurrent
                      ? 'bg-primary/10 border-primary text-primary shadow-sm ring-1 ring-primary/20'
                      : 'bg-background/60 border-border/40 text-muted-foreground opacity-70'
                  }`}
                >
                  <div className="text-[11px] font-bold flex items-center justify-center gap-1">
                    <span>Rung {r.rung}</span>
                    {isCurrent && <Sparkles className="w-3 h-3 text-primary animate-pulse" />}
                  </div>
                  <div className="text-[10px] mt-0.5 truncate">{r.name}</div>
                  <div className="text-[10px] font-medium mt-1 text-foreground/80">{r.recommendedModels}</div>
                </div>
              );
            })}
          </div>
        </div>

        {/* 跨机模拟器调节条 (可选展开) */}
        {isSimulatorOpen && (
          <div className="p-4 mx-6 my-4 bg-primary/5 rounded-lg border border-primary/20 space-y-3 animate-in fade-in duration-200">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-primary flex items-center gap-1.5">
                <Sliders className="w-3.5 h-3.5" />
                {t('simulatorTitle')}
              </span>
              <span className="text-muted-foreground">{t('simulatorDesc')}</span>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-xs font-medium whitespace-nowrap min-w-[120px]">
                {t('simulatedVram')}: <strong className="text-primary text-sm">{simulatedVram} GB</strong>
              </span>
              <input
                type="range"
                min="4"
                max="128"
                step="4"
                value={simulatedVram}
                onChange={(e) => setSimulatedVram(Number(e.target.value))}
                className="w-full accent-primary h-1.5 bg-muted rounded-lg cursor-pointer"
              />
            </div>
          </div>
        )}

        {/* 推荐列表 */}
        <div className="p-6 space-y-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-sm font-medium text-muted-foreground">{t('recommendedModels')}</h4>
          </div>

          {profile.ollama_running === false && (
            <Alert variant="destructive" className="mb-4 bg-red-500/5 border-red-500/20 text-red-600 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('ollamaNotRunningTitle')}</AlertTitle>
              <AlertDescription className="text-xs mt-1">{t('ollamaNotRunningDesc')}</AlertDescription>
            </Alert>
          )}

          <div className="grid gap-3">
            {simulatedRecommendations.map((rec, idx) => {
              const isDownloading = downloadingModel === rec.model_id;
              const isDeleting = deletingModel === rec.model_id;
              const progressPercent =
                isDownloading && downloadProgress?.total && downloadProgress?.completed
                  ? Math.round((downloadProgress.completed / downloadProgress.total) * 100)
                  : 0;

              // 预估模型大小 (GB)
              const estimatedDiskGb = rec.disk_size_gb || rec.req_vram_gb * 0.8;
              const hasEnoughDisk = profile.free_disk_gb ? profile.free_disk_gb > estimatedDiskGb : true;

              return (
                <div
                  key={rec.model_id}
                  className={`flex flex-col sm:flex-row items-start sm:items-center justify-between p-4 rounded-lg border transition-all ${
                    idx === 0 ? 'bg-primary/5 border-primary/30 shadow-sm' : 'bg-background hover:bg-muted/50'
                  }`}
                >
                  <div className="space-y-2 flex-1 pr-4 w-full">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold">{rec.name}</span>
                      {idx === 0 && (
                        <Badge className="bg-primary text-primary-foreground text-[10px] px-1.5 py-0 h-5">
                          {t('bestFit')}
                        </Badge>
                      )}
                      {rec.min_rung && (
                        <Badge variant="outline" className="text-[10px] h-5">
                          Rung {rec.min_rung}+
                        </Badge>
                      )}
                      <Badge
                        variant="secondary"
                        className="bg-primary/10 text-primary border-primary/20 text-[10px] h-5 cursor-help"
                        title={t('agenticTooltip')}
                      >
                        {t('agenticBadge')}
                      </Badge>
                    </div>
                    <p className="text-xs text-muted-foreground line-clamp-1">{rec.description}</p>

                    {/* 64K 上下文显存三色透视细分条 */}
                    <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-blue-500" />
                        <span>
                          {t('weightVram')}: {rec.weightGb} GB
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span className="w-2 h-2 rounded-full bg-emerald-500" />
                        <span>
                          {t('kvVram')}: {rec.kvQ8Gb}G(Q8) / {rec.kvFp16Gb}G(FP16)
                        </span>
                      </div>
                      <div className="flex items-center gap-1 text-foreground/90 font-medium">
                        <span>
                          {t('vram64kFp16')}: ~{rec.totalNeeded64k} GB
                        </span>
                      </div>
                      {rec.est_tok_per_sec != null && (
                        <span
                          className={`font-medium tabular-nums ${
                            rec.est_tok_per_sec >= 20
                              ? 'text-green-600 dark:text-green-400'
                              : rec.est_tok_per_sec >= 8
                                ? 'text-yellow-600 dark:text-yellow-400'
                                : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          ~{rec.est_tok_per_sec} tok/s
                        </span>
                      )}
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row items-end sm:items-center gap-4 mt-4 sm:mt-0 w-full sm:w-auto">
                    <div className="flex flex-col items-end gap-1 min-w-[100px]">
                      <div className="flex items-center gap-1.5">
                        <span className="text-xs font-medium">Fit Score:</span>
                        <span className={`text-sm font-bold ${getFitLevelColor(rec.effectiveFitLevel).split(' ')[0]}`}>
                          {rec.effectiveFitScore}%
                        </span>
                      </div>
                      <Progress
                        value={rec.effectiveFitScore}
                        className="h-1.5 w-24"
                        indicatorClassName={
                          rec.effectiveFitLevel === 'perfect' || rec.effectiveFitLevel === 'good'
                            ? 'bg-green-500'
                            : rec.effectiveFitLevel === 'fair'
                              ? 'bg-yellow-500'
                              : 'bg-red-500'
                        }
                      />
                    </div>

                    {isDownloading ? (
                      <div className="flex flex-col items-end gap-1 w-full sm:w-[150px]">
                        <div className="flex items-center justify-between w-full">
                          <span
                            className="text-[10px] text-muted-foreground truncate max-w-[120px]"
                            title={downloadProgress?.status || t('downloading')}
                          >
                            {downloadProgress?.status || t('downloading')}
                          </span>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-4 w-4 rounded-full text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                            onClick={handleCancelDownload}
                            title={t('cancel')}
                          >
                            <X className="h-3 w-3" />
                          </Button>
                        </div>
                        <Progress value={progressPercent} className="h-2 w-full" />
                      </div>
                    ) : (
                      <div className="flex items-center gap-2">
                        {rec.is_installed && (
                          <Button
                            size="icon"
                            variant="ghost"
                            className="h-8 w-8 text-muted-foreground hover:text-destructive hover:bg-destructive/10"
                            disabled={isDeleting}
                            onClick={() => handleDelete(rec.model_id)}
                            title={t('delete')}
                          >
                            {isDeleting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                          </Button>
                        )}
                        <Button
                          size="sm"
                          variant={rec.is_installed ? 'secondary' : idx === 0 ? 'default' : 'outline'}
                          className="shrink-0 min-w-[100px]"
                          disabled={
                            rec.effectiveFitLevel === 'poor' ||
                            profile.ollama_running === false ||
                            downloadingModel !== null ||
                            (!rec.is_installed && !hasEnoughDisk)
                          }
                          onClick={() => (rec.is_installed ? onApplyModel(rec.model_id) : handleDownload(rec.model_id))}
                          title={
                            !rec.is_installed && !hasEnoughDisk
                              ? t('notEnoughDisk', { required: estimatedDiskGb.toFixed(1) })
                              : undefined
                          }
                        >
                          {rec.is_installed ? (
                            t('installed')
                          ) : (
                            <>
                              <Download className="w-3.5 h-3.5 mr-1.5" />
                              {!hasEnoughDisk ? t('diskFull') : t('apply')}
                            </>
                          )}
                        </Button>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {profile.recommendations.some((r) => r.fit_level === 'poor') && (
            <Alert variant="destructive" className="mt-4 bg-red-500/5 border-red-500/20 text-red-600 dark:text-red-400">
              <AlertTriangle className="h-4 w-4" />
              <AlertTitle>{t('warningTitle')}</AlertTitle>
              <AlertDescription className="text-xs mt-1">{t('warningDesc')}</AlertDescription>
            </Alert>
          )}

          {/* 24/7 常驻与 GPU 释放最佳实践指引 */}
          <div className="mt-4 p-3.5 bg-muted/40 rounded-lg border border-border/40 text-xs text-muted-foreground">
            <span className="font-semibold text-foreground/90">{t('keepAliveTipTitle')}：</span>
            <span>{t('keepAliveTipDesc')}</span>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
