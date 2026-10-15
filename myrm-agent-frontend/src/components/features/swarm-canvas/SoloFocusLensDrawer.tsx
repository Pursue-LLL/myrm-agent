/**
 * SoloFocusLensDrawer.tsx
 * 单 Agent 聚焦透镜抽屉：全高展示子智能体思维流、实时工具轨迹与专属纠偏指令直发
 */

import React, { useMemo, useState } from 'react';
import {
  Activity,
  Bot,
  Compass,
  CornerDownLeft,
  PauseOctagon,
  Sparkles,
  Terminal,
  Wrench,
  X,
} from 'lucide-react';
import { formatWorkerStatusBadge } from './swarmCanvasEngine';
import { useSwarmCanvasStore } from './useSwarmCanvasStore';

export interface SoloFocusLensDrawerProps {
  className?: string;
  onSteer?: (workerId: string, instruction: string) => void;
  onStop?: (workerId: string) => void;
  onClose?: () => void;
}

export const SoloFocusLensDrawer: React.FC<SoloFocusLensDrawerProps> = ({
  className = '',
  onSteer,
  onStop,
  onClose,
}) => {
  const isLensDrawerOpen = useSwarmCanvasStore(
    (state) => state.isLensDrawerOpen
  );
  const focusedWorkerId = useSwarmCanvasStore(
    (state) => state.focusedWorkerId
  );
  const workers = useSwarmCanvasStore((state) => state.workers);
  const closeLens = useSwarmCanvasStore((state) => state.closeLens);
  const steerWorker = useSwarmCanvasStore((state) => state.steerWorker);
  const stopWorker = useSwarmCanvasStore((state) => state.stopWorker);

  const [steerInput, setSteerInput] = useState('');

  const worker = useMemo(() => {
    return workers.find((w) => w.id === focusedWorkerId) ?? null;
  }, [workers, focusedWorkerId]);

  if (!isLensDrawerOpen || worker === null) {
    return null;
  }

  const badgeMeta = formatWorkerStatusBadge(worker.status);

  const handleClose = (): void => {
    closeLens();
    if (onClose !== undefined) {
      onClose();
    }
  };

  const handleSendSteer = (): void => {
    const text = steerInput.trim();
    if (text === '') {
      return;
    }
    steerWorker(worker.id, text);
    if (onSteer !== undefined) {
      onSteer(worker.id, text);
    }
    setSteerInput('');
  };

  const handleStopWorker = (): void => {
    stopWorker(worker.id);
    if (onStop !== undefined) {
      onStop(worker.id);
    }
  };

  return (
    <aside
      data-testid="solo-focus-lens-drawer"
      aria-label="单智能体聚焦透镜抽屉"
      className={`fixed inset-y-0 right-0 w-full max-w-md bg-slate-900 border-l border-slate-700/80 shadow-2xl z-50 flex flex-col text-slate-200 ${className}`}
    >
      {/* 抽屉头部 */}
      <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-slate-950/70">
        <div className="flex items-center gap-2.5">
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center border"
            style={{
              backgroundColor: `${worker.colorTheme}20`,
              borderColor: worker.colorTheme,
            }}
          >
            <Bot
              className="w-4 h-4"
              style={{ color: worker.colorTheme }}
            />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold">{worker.name}</h2>
              <span
                className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${badgeMeta.badgeBg} ${badgeMeta.badgeText}`}
              >
                {badgeMeta.label}
              </span>
            </div>
            <p className="text-[10px] text-slate-400 mt-0.5">{worker.role}</p>
          </div>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            type="button"
            data-testid="lens-stop-worker-btn"
            aria-label="叫停此智能体"
            onClick={handleStopWorker}
            className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-slate-800 transition-colors"
            title="中止此子智能体任务"
          >
            <PauseOctagon className="w-4 h-4" />
          </button>
          <button
            type="button"
            data-testid="close-lens-drawer-btn"
            aria-label="关闭透镜抽屉"
            onClick={handleClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 当前攻坚任务条 */}
      <div className="px-4 py-2.5 bg-slate-950/40 border-b border-slate-800 text-xs">
        <span className="text-[10px] text-slate-500 font-semibold block">
          正在攻坚任务:
        </span>
        <span className="text-slate-200 font-medium mt-0.5 block">
          {worker.currentTaskTitle}
        </span>
      </div>

      {/* 滚动内容区：思维流与工具轨迹 */}
      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4 text-xs">
        {/* 专属思维流 Thinking 流 */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 font-semibold text-slate-300">
            <Sparkles className="w-3.5 h-3.5 text-amber-400" />
            <span>智能体专属思维流 (Thinking Trail):</span>
          </div>
          <div
            data-testid="lens-thinking-logs-list"
            className="bg-slate-950/80 rounded-xl p-3 border border-slate-800 font-mono text-[11px] text-slate-300 flex flex-col gap-1.5 max-h-48 overflow-y-auto"
          >
            {worker.thinkingLogs.length === 0 ? (
              <span className="text-slate-500">就绪中，暂无思考流</span>
            ) : (
              worker.thinkingLogs.map((log, idx) => (
                <div key={idx} className="flex items-start gap-1.5">
                  <span className="text-amber-500 font-bold shrink-0 mt-0.5">
                    ›
                  </span>
                  <span className="leading-relaxed">{log}</span>
                </div>
              ))
            )}
          </div>
        </div>

        {/* 专属工具调用轨迹 ToolCalls */}
        <div className="flex flex-col gap-2">
          <div className="flex items-center gap-1.5 font-semibold text-slate-300">
            <Wrench className="w-3.5 h-3.5 text-blue-400" />
            <span>实时工具调用轨迹 ({worker.toolCalls.length}):</span>
          </div>
          <div
            data-testid="lens-tool-calls-list"
            className="flex flex-col gap-2"
          >
            {worker.toolCalls.length === 0 ? (
              <div className="text-[11px] text-slate-500 bg-slate-950/40 p-3 rounded-lg border border-slate-850 text-center">
                暂未发起底层工具调用
              </div>
            ) : (
              worker.toolCalls.map((tc) => (
                <div
                  key={tc.id}
                  className="p-2.5 rounded-xl bg-slate-950 border border-slate-800 flex flex-col gap-1 text-[11px]"
                >
                  <div className="flex items-center justify-between font-mono font-bold text-blue-400">
                    <span className="flex items-center gap-1">
                      <Terminal className="w-3 h-3 text-slate-500" />
                      <span>{tc.toolName}</span>
                    </span>
                    {tc.durationMs !== undefined && (
                      <span className="text-[10px] text-slate-500 font-normal">
                        {tc.durationMs}ms
                      </span>
                    )}
                  </div>
                  <span className="text-slate-300 text-[10px]">
                    {tc.summary}
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>

      {/* 底部专属纠偏指令输入区 */}
      <div className="p-3.5 border-t border-slate-800 bg-slate-950/80 flex flex-col gap-2">
        <label
          htmlFor="lens-steer-input"
          className="text-[11px] font-medium text-slate-400 flex items-center gap-1"
        >
          <Compass className="w-3 h-3 text-emerald-400" />
          <span>针对此子智能体定向纠偏 (Steer):</span>
        </label>
        <div className="flex items-center gap-2">
          <input
            id="lens-steer-input"
            data-testid="lens-steer-input"
            type="text"
            value={steerInput}
            onChange={(e) => setSteerInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                handleSendSteer();
              }
            }}
            placeholder="例如：'重点提取第二季度的客单价数据'..."
            className="flex-1 text-xs bg-slate-950 border border-slate-700/80 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-blue-500"
          />
          <button
            type="button"
            data-testid="lens-send-steer-btn"
            disabled={steerInput.trim() === ''}
            onClick={handleSendSteer}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed shadow transition-colors"
          >
            <CornerDownLeft className="w-3.5 h-3.5" />
            <span>纠偏</span>
          </button>
        </div>
      </div>
    </aside>
  );
};
