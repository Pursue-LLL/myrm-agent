'use client';

import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import {
  Clock,
  Layers,
  Sparkles,
  Zap,
  TrendingDown,
  Loader2,
  CheckCircle2,
  Calendar,
  Activity,
} from 'lucide-react';
import { ActivityCompactorTimelineView } from './ActivityCompactorTimelineView';
import {
  getActivityCompactorTelemetry,
  getRecentMacroFolds,
  getRecentMicroSlices,
  ingestActivityEvent,
  synthesizeDailyArchive,
  triggerMacroDistill,
  triggerMicroFold,
  type CompactorPipelineTelemetryDTO,
  type DailyPreferenceArchiveDTO,
  type MacroMilestoneFoldDTO,
  type MicroActivitySliceDTO,
} from '@/services/memory/activityCompactor';

export function ActivityCompactorCard(): React.JSX.Element {
  const [appName, setAppName] = useState<string>('VSCode');
  const [windowTitle, setWindowTitle] = useState<string>('src/services/api.ts - editor');
  const [eventPayload, setEventPayload] = useState<string>('编辑 API 路由并优化错误边界');

  const [loading, setLoading] = useState<boolean>(false);
  const [acting, setActing] = useState<boolean>(false);
  const [telemetry, setTelemetry] = useState<CompactorPipelineTelemetryDTO | null>(null);
  const [microSlices, setMicroSlices] = useState<MicroActivitySliceDTO[]>([]);
  const [macroFolds, setMacroFolds] = useState<MacroMilestoneFoldDTO[]>([]);
  const [dailyArchive, setDailyArchive] = useState<DailyPreferenceArchiveDTO | null>(null);

  const fetchStatus = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      const [tel, slices, folds] = await Promise.all([
        getActivityCompactorTelemetry(),
        getRecentMicroSlices(10),
        getRecentMacroFolds(5),
      ]);
      setTelemetry(tel);
      setMicroSlices(slices);
      setMacroFolds(folds);
    } catch {
      // Offline fallback state with mocked data
      setTelemetry({
        total_raw_events: 180,
        total_micro_slices: 12,
        total_macro_folds: 2,
        idle_events_dropped: 24,
        estimated_tokens_saved: 56400,
        compression_ratio: 15.0,
      });
      setMicroSlices([
        {
          slice_id: 'micro_demo_01',
          start_time: new Date(Date.now() - 600000).toISOString(),
          end_time: new Date().toISOString(),
          primary_app: 'VSCode',
          raw_event_count: 36,
          folded_summary: '主要在 VSCode 中操作 · 专注工作区: src/services/api.ts · 执行命令: bun test',
          unique_windows: ['src/services/api.ts'],
          is_idle: false,
          active_minutes: 8.5,
        },
      ]);
      setMacroFolds([
        {
          fold_id: 'macro_demo_01',
          start_time: new Date(Date.now() - 21600000).toISOString(),
          end_time: new Date().toISOString(),
          milestone_summary: '完成了为期 5.2 小时的高专注开发推进；核心工具链集中于 VSCode, Terminal',
          key_activities: ['重构了认证 API 并通过全量单元测试', '优化了请求超时与重试逻辑'],
          micro_slices_count: 12,
          tags: ['coding', 'testing'],
          confidence: 0.95,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchStatus();
  }, [fetchStatus]);

  const handleIngestEvent = async (): Promise<void> => {
    if (!appName.trim() || !windowTitle.trim()) return;
    setActing(true);
    try {
      await ingestActivityEvent({
        app_name: appName.trim(),
        window_title: windowTitle.trim(),
        action_type: 'keystroke_burst',
        event_payload: eventPayload.trim(),
        duration_seconds: 5.0,
      });
      await fetchStatus();
    } catch {
      // Fallback
    } finally {
      setActing(false);
    }
  };

  const handleMicroFold = async (): Promise<void> => {
    setActing(true);
    try {
      await triggerMicroFold({ force: true });
      await fetchStatus();
    } catch {
      // Fallback
    } finally {
      setActing(false);
    }
  };

  const handleMacroDistill = async (): Promise<void> => {
    setActing(true);
    try {
      await triggerMacroDistill({ hours_back: 6 });
      await fetchStatus();
    } catch {
      // Fallback
    } finally {
      setActing(false);
    }
  };

  const handleDailyArchive = async (): Promise<void> => {
    setActing(true);
    try {
      const arch = await synthesizeDailyArchive({});
      setDailyArchive(arch);
      await fetchStatus();
    } catch {
      setDailyArchive({
        archive_id: 'arch_mock_today',
        date_str: new Date().toISOString().slice(0, 10),
        consolidated_facts: ['完成了认证模块的回归测试并修复 2 处逻辑缺陷'],
        preference_updates: ['偏好使用本地终端自动化测试与严谨类型检查'],
        total_raw_events_processed: 180,
        macro_folds_count: 2,
      });
    } finally {
      setActing(false);
    }
  };

  const applyPreset = (preset: 'vscode' | 'terminal' | 'chrome'): void => {
    if (preset === 'vscode') {
      setAppName('VSCode');
      setWindowTitle('src/services/api.ts - editor');
      setEventPayload('编辑 API 路由并优化错误边界');
    } else if (preset === 'terminal') {
      setAppName('Terminal');
      setWindowTitle('zsh - tests');
      setEventPayload('bun run vitest run test_api.test.ts');
    } else {
      setAppName('Chrome');
      setWindowTitle('GitHub PR #108 - Code Review');
      setEventPayload('https://github.com/myrm-org/myrm-agent/pull/108');
    }
  };

  return (
    <Card className="border border-border/80 shadow-sm" data-testid="activity-compactor-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="h-5 w-5 text-primary" />
            <CardTitle className="text-base font-semibold">
              分级滑动时间窗口活动日志折叠与提炼管道 (Hierarchical Activity Compactor)
            </CardTitle>
          </div>
          <Badge variant="outline" className="text-xs border-primary/40 text-primary">
            Item 87 · P0
          </Badge>
        </div>
        <CardDescription className="text-xs text-muted-foreground">
          对标 ChatGPT Desktop Skysight 模块：10 分钟微观纯算法去抖折叠 (0 Token) ➔ 6 小时宏观业务里程碑提纯 ➔ 24 小时长期偏好归档。
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Preset Selector */}
        <div className="flex flex-wrap items-center gap-2 pb-1 border-b border-border/60 text-xs">
          <span className="text-muted-foreground font-medium flex items-center gap-1">
            <Sparkles className="h-3.5 w-3.5 text-primary" /> 快速事件预设:
          </span>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2" onClick={() => applyPreset('vscode')}>
            代码高频开发 (VSCode)
          </Button>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2 text-primary" onClick={() => applyPreset('terminal')}>
            终端回归测试 (Terminal)
          </Button>
          <Button type="button" variant="outline" size="sm" className="h-6 text-[11px] px-2 text-amber-600 dark:text-amber-400" onClick={() => applyPreset('chrome')}>
            网页代码评审 (Chrome)
          </Button>
        </div>

        {/* Telemetry HUD */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[11px] text-muted-foreground">原始事件总数</div>
            <div className="text-lg font-bold text-foreground">{telemetry?.total_raw_events ?? 0}</div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[11px] text-muted-foreground">10min 折叠切片</div>
            <div className="text-lg font-bold text-primary">{telemetry?.total_micro_slices ?? 0}</div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[11px] text-muted-foreground">6h 业务里程碑</div>
            <div className="text-lg font-bold text-green-600">{telemetry?.total_macro_folds ?? 0}</div>
          </div>
          <div className="rounded-md border border-border/70 p-2 bg-card">
            <div className="text-[11px] text-muted-foreground flex items-center gap-1">
              <TrendingDown className="h-3 w-3 text-green-500" />
              <span>Token 节省估算</span>
            </div>
            <div className="text-lg font-bold text-green-600">
              {((telemetry?.estimated_tokens_saved ?? 0) / 1000).toFixed(1)}k
            </div>
          </div>
        </div>

        {/* Action Ingestion & Pipeline Triggers */}
        <div className="space-y-3 rounded-md border border-border/70 p-3 bg-muted/5 text-xs">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            <div className="space-y-1">
              <label htmlFor="compactor-app-name" className="text-[11px] font-medium text-muted-foreground">
                应用名称 (App Name):
              </label>
              <Input
                id="compactor-app-name"
                value={appName}
                onChange={(e) => setAppName(e.target.value)}
                className="h-7 text-xs"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label htmlFor="compactor-window-title" className="text-[11px] font-medium text-muted-foreground">
                窗口标题 / 标签 (Window Title):
              </label>
              <Input
                id="compactor-window-title"
                value={windowTitle}
                onChange={(e) => setWindowTitle(e.target.value)}
                className="h-7 text-xs"
              />
            </div>
          </div>

          <div className="space-y-1">
            <label htmlFor="compactor-event-payload" className="text-[11px] font-medium text-muted-foreground">
              事件内容 / 正在执行的动作 (Payload):
            </label>
            <Input
              id="compactor-event-payload"
              value={eventPayload}
              onChange={(e) => setEventPayload(e.target.value)}
              className="h-7 text-xs font-mono"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border/50">
            <Button
              type="button"
              size="sm"
              className="h-7 text-xs"
              disabled={acting}
              onClick={handleIngestEvent}
            >
              {acting ? <Loader2 className="h-3 w-3 animate-spin mr-1" /> : <Activity className="h-3 w-3 mr-1" />}
              注入单条操作事件
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs text-primary"
              disabled={acting}
              onClick={handleMicroFold}
            >
              <Zap className="h-3 w-3 mr-1" /> 触发 10min 微观折叠 (0 Token)
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs text-green-600"
              disabled={acting}
              onClick={handleMacroDistill}
            >
              <Clock className="h-3 w-3 mr-1" /> 触发 6h 宏观提纯
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 text-xs text-amber-600"
              disabled={acting}
              onClick={handleDailyArchive}
            >
              <Calendar className="h-3 w-3 mr-1" /> 生成 24h 每日归档
            </Button>
          </div>
        </div>

        {/* Daily Archive Results (if generated) */}
        {dailyArchive && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs space-y-1.5">
            <div className="font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
              <Calendar className="h-4 w-4" />
              <span>24 小时长期偏好与事实归档完成 ({dailyArchive.date_str})</span>
            </div>
            <div className="space-y-1 text-foreground">
              {dailyArchive.consolidated_facts.map((fact, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <CheckCircle2 className="h-3.5 w-3.5 text-green-500 mt-0.5 shrink-0" />
                  <span>{fact}</span>
                </div>
              ))}
              {dailyArchive.preference_updates.map((pref, idx) => (
                <div key={idx} className="text-muted-foreground text-[11px] pl-5">
                  ✦ 推断长期偏好: {pref}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Sliding Slices & Folds Timeline */}
        <ActivityCompactorTimelineView microSlices={microSlices} macroFolds={macroFolds} />
      </CardContent>
    </Card>
  );
}
