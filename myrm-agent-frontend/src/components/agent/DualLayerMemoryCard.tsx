/**
 * [INPUT]
 * - @/services/memory/profileNotes: getProfileNotesContents, updateProfileNotesContents, checkProfileNotesIntake
 * - @/services/memory/profileNotes: LayerWatermarkResponse, WatermarkLevel, ProfileNotesIntakeResponse
 * - @/components/primitives: Card, Button, Badge, Textarea, Input
 *
 * [OUTPUT]
 * - DualLayerMemoryCard: React component rendering User Profile & Agent Notes dual HUD with watermark gauges and intake filter probe.
 *
 * [POS]
 * Reusable agent memory dashboard component enforcing Hermes-grade capacity limits (USER <= 1375c, MEMORY <= 2200c)
 * and noise purging verification. Strict typing applied: No `any` types allowed.
 */

'use client';

import React, { useCallback, useEffect, useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Filter,
  Loader2,
  RefreshCw,
  Save,
  ShieldCheck,
  User,
  Wrench,
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
import { Textarea } from '@/components/primitives/textarea';
import { cn } from '@/lib/utils/classnameUtils';
import {
  checkProfileNotesIntake,
  getProfileNotesContents,
  type LayerWatermarkResponse,
  type ProfileNotesIntakeResponse,
  updateProfileNotesContents,
  type WatermarkLevel,
} from '@/services/memory/profileNotes';

interface DualLayerMemoryCardProps {
  className?: string;
  onSaved?: () => void;
}

const DEFAULT_USER_MAX = 1375;
const DEFAULT_MEMORY_MAX = 2200;

function getWatermarkBadge(level: WatermarkLevel): {
  label: string;
  variant: 'default' | 'secondary' | 'destructive' | 'outline';
  className: string;
} {
  switch (level) {
    case 'safe':
      return { label: '正常 (SAFE)', variant: 'default', className: 'bg-emerald-600 text-white' };
    case 'warning':
      return { label: '预警 (WARNING)', variant: 'secondary', className: 'bg-amber-500 text-white' };
    case 'critical':
      return { label: '临界 (CRITICAL)', variant: 'secondary', className: 'bg-orange-600 text-white' };
    case 'overflow':
      return { label: '超限 (OVERFLOW)', variant: 'destructive', className: 'bg-rose-600 text-white' };
    default:
      return { label: level, variant: 'outline', className: '' };
  }
}

function WatermarkBar({ watermark }: { watermark: LayerWatermarkResponse }) {
  const percent = Math.min(Math.round(watermark.usage_ratio * 100), 100);
  const badgeInfo = getWatermarkBadge(watermark.level);

  const getBarColor = (level: WatermarkLevel) => {
    switch (level) {
      case 'safe':
        return 'bg-emerald-500';
      case 'warning':
        return 'bg-amber-500';
      case 'critical':
        return 'bg-orange-500';
      case 'overflow':
        return 'bg-rose-600';
      default:
        return 'bg-primary';
    }
  };

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between text-xs font-medium">
        <span className="text-muted-foreground">
          容量水位: {watermark.current_chars} / {watermark.max_chars} 字符 ({percent}%)
        </span>
        <Badge variant={badgeInfo.variant} className={cn('text-[10px] px-1.5 py-0', badgeInfo.className)}>
          {badgeInfo.label}
        </Badge>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-secondary">
        <div
          className={cn('h-full transition-all duration-300', getBarColor(watermark.level))}
          style={{ width: `${percent}%` }}
        />
      </div>
      {watermark.warning_message && (
        <p className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
          <AlertTriangle className="h-3 w-3 shrink-0" />
          <span>{watermark.warning_message}</span>
        </p>
      )}
    </div>
  );
}

export function DualLayerMemoryCard({ className, onSaved }: DualLayerMemoryCardProps) {
  const [userContent, setUserContent] = useState('');
  const [memoryContent, setMemoryContent] = useState('');
  const [userWatermark, setUserWatermark] = useState<LayerWatermarkResponse>({
    layer: 'user',
    current_chars: 0,
    max_chars: DEFAULT_USER_MAX,
    usage_ratio: 0,
    level: 'safe',
    warning_message: null,
  });
  const [memoryWatermark, setMemoryWatermark] = useState<LayerWatermarkResponse>({
    layer: 'memory',
    current_chars: 0,
    max_chars: DEFAULT_MEMORY_MAX,
    usage_ratio: 0,
    level: 'safe',
    warning_message: null,
  });

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [feedbackMsg, setFeedbackMsg] = useState<string | null>(null);

  // Intake test probe states
  const [testProbeText, setTestProbeText] = useState('');
  const [isProbing, setIsProbing] = useState(false);
  const [probeResult, setProbeResult] = useState<ProfileNotesIntakeResponse | null>(null);

  const fetchContents = useCallback(async () => {
    setIsLoading(true);
    setFeedbackMsg(null);
    try {
      const data = await getProfileNotesContents();
      setUserContent(data.user_content);
      setMemoryContent(data.memory_content);
      setUserWatermark(data.user_watermark);
      setMemoryWatermark(data.memory_watermark);
    } catch {
      setFeedbackMsg('加载双层记忆失败，请检查网络或后端状态');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchContents();
  }, [fetchContents]);

  const handleSave = async () => {
    setIsSaving(true);
    setFeedbackMsg(null);
    try {
      const updated = await updateProfileNotesContents({
        user_content: userContent,
        memory_content: memoryContent,
      });
      setUserContent(updated.user_content);
      setMemoryContent(updated.memory_content);
      setUserWatermark(updated.user_watermark);
      setMemoryWatermark(updated.memory_watermark);
      setFeedbackMsg('双层记忆已成功同步保存');
      onSaved?.();
    } catch {
      setFeedbackMsg('保存双层记忆失败，容量可能超限或内容不合规');
    } finally {
      setIsSaving(false);
    }
  };

  const handleProbeIntake = async () => {
    if (!testProbeText.trim()) {
      return;
    }
    setIsProbing(true);
    try {
      const res = await checkProfileNotesIntake({ content: testProbeText.trim() });
      setProbeResult(res);
    } catch {
      setProbeResult({
        accepted: false,
        target_layer: null,
        rejected_reason: '网络或服务器错误，准入检测失败',
        garbage_category: 'ERROR',
      });
    } finally {
      setIsProbing(false);
    }
  };

  return (
    <Card className={cn('w-full border border-border shadow-sm', className)}>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck className="h-5 w-5 text-primary" />
            <div>
              <CardTitle className="text-base font-semibold">
                双层画像与智能体笔记结构化看板 (Dual-Layer Memory HUD)
              </CardTitle>
              <CardDescription className="text-xs">
                Hermes 级显式分层与容量水位治理：USER ≤ 1,375c（长期偏好），MEMORY ≤ 2,200c（领域笔记）
              </CardDescription>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => void fetchContents()}
              disabled={isLoading || isSaving}
              className="h-8 gap-1 px-2 text-xs"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', isLoading && 'animate-spin')} />
              刷新
            </Button>
            <Button
              size="sm"
              onClick={() => void handleSave()}
              disabled={isLoading || isSaving}
              className="h-8 gap-1 px-3 text-xs"
            >
              {isSaving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              保存记忆
            </Button>
          </div>
        </div>
        {feedbackMsg && (
          <div className="mt-2 rounded-md bg-secondary/50 px-2.5 py-1.5 text-xs text-muted-foreground">
            {feedbackMsg}
          </div>
        )}
      </CardHeader>

      <CardContent className="space-y-4 pt-1">
        {/* Dual columns */}
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {/* Left column: User profile */}
          <div className="space-y-2 rounded-lg border border-border/80 bg-background/50 p-3">
            <div className="flex items-center gap-1.5">
              <User className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">User Profile (用户长期偏好)</span>
              <span className="text-[11px] text-muted-foreground">≤ 1,375 字符</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              跨智能体共享：母语、编码习惯、缩进排版、核心禁忌与沟通偏好。
            </p>
            <WatermarkBar watermark={userWatermark} />
            <Textarea
              className="min-h-[140px] resize-y font-mono text-xs leading-relaxed"
              placeholder="例如：母语为中文，偏好 Python PEP8 规范，严禁使用 Any 类型，交付代码单文件不超过 400 行..."
              value={userContent}
              onChange={(e) => {
                const text = e.target.value;
                setUserContent(text);
                const chars = text.length;
                const ratio = chars / DEFAULT_USER_MAX;
                let lvl: WatermarkLevel = 'safe';
                if (ratio > 1.0) {
                  lvl = 'overflow';
                } else if (ratio >= 0.9) {
                  lvl = 'critical';
                } else if (ratio >= 0.7) {
                  lvl = 'warning';
                }
                setUserWatermark((prev) => ({
                  ...prev,
                  current_chars: chars,
                  usage_ratio: ratio,
                  level: lvl,
                }));
              }}
              disabled={isLoading}
            />
          </div>

          {/* Right column: Agent working notes */}
          <div className="space-y-2 rounded-lg border border-border/80 bg-background/50 p-3">
            <div className="flex items-center gap-1.5">
              <Wrench className="h-4 w-4 text-primary" />
              <span className="text-sm font-semibold">Agent Notes (智能体专属笔记)</span>
              <span className="text-[11px] text-muted-foreground">≤ 2,200 字符</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              当前智能体专属：项目架构规范、高频专业术语、边界要求与工程排障要领。
            </p>
            <WatermarkBar watermark={memoryWatermark} />
            <Textarea
              className="min-h-[140px] resize-y font-mono text-xs leading-relaxed"
              placeholder="例如：本项目遵循 Clean Architecture，harness 框架层与 server 业务层严禁反向依赖..."
              value={memoryContent}
              onChange={(e) => {
                const text = e.target.value;
                setMemoryContent(text);
                const chars = text.length;
                const ratio = chars / DEFAULT_MEMORY_MAX;
                let lvl: WatermarkLevel = 'safe';
                if (ratio > 1.0) {
                  lvl = 'overflow';
                } else if (ratio >= 0.9) {
                  lvl = 'critical';
                } else if (ratio >= 0.7) {
                  lvl = 'warning';
                }
                setMemoryWatermark((prev) => ({
                  ...prev,
                  current_chars: chars,
                  usage_ratio: ratio,
                  level: lvl,
                }));
              }}
              disabled={isLoading}
            />
          </div>
        </div>

        {/* Bottom: Intake Filter Probe */}
        <div className="rounded-lg border border-dashed border-border bg-muted/20 p-3">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-muted-foreground mb-2">
            <Filter className="h-3.5 w-3.5 text-primary" />
            <span>短期垃圾记忆准入试算探针 (Intake Purge Guard Tester)</span>
          </div>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Input
              className="h-8 text-xs font-mono"
              placeholder="输入候选记忆（如: 'Phase 2 completed'、'PR #882'、'Traceback...' 或 '偏好 PEP8'）"
              value={testProbeText}
              onChange={(e) => setTestProbeText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  e.preventDefault();
                  void handleProbeIntake();
                }
              }}
            />
            <Button
              variant="secondary"
              size="sm"
              onClick={() => void handleProbeIntake()}
              disabled={isProbing || !testProbeText.trim()}
              className="h-8 shrink-0 text-xs gap-1"
            >
              {isProbing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
              检测准入
            </Button>
          </div>

          {probeResult && (
            <div
              className={cn(
                'mt-2 flex items-start gap-2 rounded-md p-2 text-xs',
                probeResult.accepted
                  ? 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300'
                  : 'bg-rose-50 text-rose-800 dark:bg-rose-950/40 dark:text-rose-300',
              )}
            >
              {probeResult.accepted ? (
                <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
              ) : (
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600 dark:text-rose-400" />
              )}
              <div className="space-y-0.5">
                <div className="font-medium">
                  {probeResult.accepted
                    ? `准入放行: 路由至 ${probeResult.target_layer?.toUpperCase() ?? 'LONG-TERM'} 层`
                    : `准入拒绝: 判定为短期瞬态垃圾 [${probeResult.garbage_category ?? 'TRANSIENT'}]`}
                </div>
                {probeResult.rejected_reason && (
                  <p className="text-[11px] opacity-90">{probeResult.rejected_reason}</p>
                )}
              </div>
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
export default DualLayerMemoryCard;
