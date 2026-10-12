/**
 * [INPUT]
 * @/services/memory/experienceObservability
 *
 * [OUTPUT]
 * ZeroRefactorPluginConsoleView: Configuration and simulation console for zero-refactor
 * host lifecycle plugin and three-way integration (Plugin, MCP, Skill).
 *
 * [POS]
 * Sub-view of Item 108 ExperienceObservabilityStudioCard.
 * Strict typing applied, zero any, file length < 350 lines.
 */

import React, { useState } from 'react';
import {
  Plug,
  Save,
  Play,
  RotateCcw,
  CheckCircle2,
  Sparkles,
  Server,
  Terminal,
  Zap,
} from 'lucide-react';
import type {
  HostAccessChannel,
  HostPluginConfigDTO,
} from '@/services/memory/experienceObservability';
import { updatePluginConfig } from '@/services/memory/experienceObservability';

interface ZeroRefactorPluginConsoleViewProps {
  initialConfig: HostPluginConfigDTO;
  onConfigUpdated: (updated: HostPluginConfigDTO) => void;
}

export const ZeroRefactorPluginConsoleView: React.FC<
  ZeroRefactorPluginConsoleViewProps
> = ({ initialConfig, onConfigUpdated }) => {
  const [config, setConfig] = useState<HostPluginConfigDTO>(initialConfig);
  const [isSaving, setIsSaving] = useState(false);
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [simulationLog, setSimulationLog] = useState<string | null>(null);

  const handleSaveConfig = async () => {
    setIsSaving(true);
    setSaveNotice(null);
    try {
      const updated = await updatePluginConfig({
        enabled: config.enabled,
        active_channel: config.active_channel,
        auto_warmup: config.auto_warmup,
        auto_capture: config.auto_capture,
        auto_commit: config.auto_commit,
        monitored_host: config.monitored_host,
      });
      setConfig(updated);
      onConfigUpdated(updated);
      setSaveNotice('宿主插件运行时配置已成功刷盘生效！');
    } catch {
      // Local fallback
      onConfigUpdated(config);
      setSaveNotice('（本地仿真）插件运行时配置已成功保存！');
    } finally {
      setIsSaving(false);
    }
  };

  const handleSimulateLifecycle = (eventKind: string) => {
    if (eventKind === 'session_start') {
      setSimulationLog(
        `[Session Start] 宿主 ${config.monitored_host} 初始化会话 -> 触发 auto_warmup: 预热召回 Top 经验条目 (proc_git_push_safe, RET-EXC-01) 注入 KV Cache。`,
      );
    } else if (eventKind === 'task_completed') {
      setSimulationLog(
        `[Task Completed] 宿主 ${config.monitored_host} 任务边界触发 -> auto_commit 启动两阶段归档与 MemoryDiff 变更审计，任务零阻塞。`,
      );
    } else {
      setSimulationLog(`[Event Captured] 宿主 ${config.monitored_host} 事件已记录。`);
    }
  };

  const channels: { id: HostAccessChannel; label: string; desc: string }[] = [
    {
      id: 'plugin',
      label: '官方零改造插件 (Plugin)',
      desc: '借宿主生命周期全自动捕获、预热与归档，业务代码零改造',
    },
    {
      id: 'mcp',
      label: 'Direct FC 标准服务 (MCP)',
      desc: '标准 MCP 协议服务，外部自主 Agent 标准调用，严禁第三路径',
    },
    {
      id: 'skill',
      label: '经验规约技能 (Skill)',
      desc: 'PTC 渐进式披露，针对高价值任务前显式检索读经验',
    },
  ];

  return (
    <div className="space-y-4">
      {/* Three-Way Integration Architecture Banner */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {channels.map((ch) => {
          const isActive = config.active_channel === ch.id;
          return (
            <button
              key={ch.id}
              type="button"
              onClick={() => setConfig({ ...config, active_channel: ch.id })}
              className={`p-3 rounded-lg border text-left transition-all flex flex-col justify-between focus:outline-none focus:ring-2 focus:ring-primary ${
                isActive
                  ? 'bg-primary/5 border-primary shadow-sm'
                  : 'bg-background border-border/60 hover:bg-muted/30'
              }`}
            >
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold text-foreground">
                    {ch.label}
                  </span>
                  {isActive && (
                    <CheckCircle2 className="w-3.5 h-3.5 text-primary" />
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground leading-relaxed">
                  {ch.desc}
                </p>
              </div>
              <div className="mt-2 text-[10px] font-mono text-muted-foreground">
                Channel: {ch.id}
              </div>
            </button>
          );
        })}
      </div>

      {/* Configuration & Lifecycle Hook Simulation Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Left: Configuration Form */}
        <div className="p-3.5 bg-background rounded-lg border border-border/60 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Plug className="w-3.5 h-3.5 text-primary" />
              宿主生命周期插件配置
            </span>
            <button
              type="button"
              onClick={handleSaveConfig}
              disabled={isSaving}
              className="flex items-center gap-1.5 px-3 py-1 text-xs font-medium bg-primary text-primary-foreground rounded hover:bg-primary/90 disabled:opacity-50 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
            >
              <Save className="w-3.5 h-3.5" />
              {isSaving ? '保存中...' : '保存配置'}
            </button>
          </div>

          <div className="space-y-2.5 text-xs">
            <div>
              <label
                htmlFor="plugin-monitored-host"
                className="text-muted-foreground block text-[11px] mb-1"
              >
                目标宿主环境 (Monitored Host)
              </label>
              <select
                id="plugin-monitored-host"
                value={config.monitored_host}
                onChange={(e) =>
                  setConfig({ ...config, monitored_host: e.target.value })
                }
                className="w-full px-2 py-1.5 rounded bg-muted/40 border border-border focus:outline-none focus:ring-2 focus:ring-primary text-xs"
              >
                <option value="claude_code">Claude Code (CLI / TUI)</option>
                <option value="cursor">Cursor (IDE Extension)</option>
                <option value="openclaw">OpenClaw (Autonomous Daemon)</option>
                <option value="hermes">Hermes Agent</option>
                <option value="generic_agent_host">Generic Agent Host</option>
              </select>
            </div>

            <div className="space-y-2 pt-2 border-t border-border/40">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.enabled}
                  onChange={(e) =>
                    setConfig({ ...config, enabled: e.target.checked })
                  }
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <span>启用插件生命周期拦截 (enabled)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.auto_warmup}
                  onChange={(e) =>
                    setConfig({ ...config, auto_warmup: e.target.checked })
                  }
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <span>会话初始化经验预热召回 (auto_warmup)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.auto_capture}
                  onChange={(e) =>
                    setConfig({ ...config, auto_capture: e.target.checked })
                  }
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <span>无侵入消息与工具执行切片捕获 (auto_capture)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={config.auto_commit}
                  onChange={(e) =>
                    setConfig({ ...config, auto_commit: e.target.checked })
                  }
                  className="rounded border-border text-primary focus:ring-primary"
                />
                <span>任务完成边界自动两阶段归档提交 (auto_commit)</span>
              </label>
            </div>
          </div>

          {saveNotice && (
            <div className="text-xs p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded border border-emerald-500/20 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              {saveNotice}
            </div>
          )}
        </div>

        {/* Right: Lifecycle Event Simulator */}
        <div className="p-3.5 bg-background rounded-lg border border-border/60 flex flex-col justify-between space-y-3">
          <div className="space-y-3">
            <span className="text-xs font-semibold text-foreground flex items-center gap-1.5">
              <Zap className="w-3.5 h-3.5 text-amber-500" />
              宿主生命周期事件演练模拟器
            </span>
            <p className="text-xs text-muted-foreground leading-relaxed">
              无需运行实际宿主进程，一键模拟宿主生命周期事件，验证经验召回与提交行为。
            </p>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => handleSimulateLifecycle('session_start')}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-muted text-foreground rounded hover:bg-muted/80 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <Play className="w-3 h-3 text-primary" />
                模拟 Session Start 预热
              </button>
              <button
                type="button"
                onClick={() => handleSimulateLifecycle('task_completed')}
                className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-muted text-foreground rounded hover:bg-muted/80 transition-colors focus:outline-none focus:ring-2 focus:ring-primary"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                模拟 Task Commit 提交
              </button>
            </div>

            {simulationLog ? (
              <div className="p-2.5 bg-muted/30 rounded border border-border/50 text-xs font-mono text-foreground leading-relaxed break-all">
                {simulationLog}
              </div>
            ) : (
              <div className="text-xs text-muted-foreground py-6 text-center">
                点击上方按钮模拟宿主生命周期钩子执行
              </div>
            )}
          </div>

          <div className="text-[10px] text-muted-foreground font-mono pt-2 border-t border-border/40">
            OpenViking 零改造接入哲学 · 杜绝业务代码入侵
          </div>
        </div>
      </div>
    </div>
  );
};
