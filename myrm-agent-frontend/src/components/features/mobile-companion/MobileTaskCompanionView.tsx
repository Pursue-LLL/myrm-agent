import React from 'react';
import {
  Smartphone,
  Radio,
  Clock,
  FileCode,
  FileText,
  FileArchive,
  Download,
  Image as ImageIcon,
  CheckCircle2,
} from 'lucide-react';
import { useMobileCompanionStore } from './useMobileCompanionStore';
import {
  formatTimeRemaining,
  getPhaseBadgeInfo,
} from './mobileCompanionEngine';
import { MobileRemoteSteeringBar } from './MobileRemoteSteeringBar';
import { CompanionArtifact } from './mobileCompanionTypes';

export interface MobileTaskCompanionViewProps {
  onDownloadArtifact?: (artifact: CompanionArtifact) => void;
  className?: string;
}

export const MobileTaskCompanionView: React.FC<MobileTaskCompanionViewProps> = ({
  onDownloadArtifact,
  className = '',
}) => {
  const { activeTask, isConnected } = useMobileCompanionStore();

  if (!activeTask) {
    return (
      <div
        data-testid="mobile-task-companion-view"
        className="min-h-screen bg-zinc-950 text-zinc-100 flex flex-col items-center justify-center p-6 text-center"
      >
        <Smartphone className="w-12 h-12 text-zinc-600 mb-3 animate-pulse" />
        <h3 className="text-sm font-semibold text-zinc-300">暂无活跃的长任务会话</h3>
        <p className="text-xs text-zinc-500 mt-1">请在电脑端启动任务并扫码配对</p>
      </div>
    );
  }

  const phaseBadge = getPhaseBadgeInfo(activeTask.phase);
  const timeRemainingStr = formatTimeRemaining(activeTask.estimatedSecondsRemaining);

  const renderArtifactIcon = (type: CompanionArtifact['type']) => {
    if (type === 'code') {
      return <FileCode className="w-4 h-4 text-cyan-400" />;
    }
    if (type === 'bundle') {
      return <FileArchive className="w-4 h-4 text-amber-400" />;
    }
    return <FileText className="w-4 h-4 text-indigo-400" />;
  };

  const handleDownload = (artifact: CompanionArtifact) => {
    if (onDownloadArtifact) {
      onDownloadArtifact(artifact);
    }
  };

  return (
    <div
      data-testid="mobile-task-companion-view"
      className={`min-h-screen bg-zinc-950 text-zinc-100 flex flex-col pb-28 font-sans ${className}`}
    >
      {/* 1. 顶部移动端状态导航条 */}
      <header className="sticky top-0 z-30 flex items-center justify-between px-4 py-3 bg-zinc-900/90 backdrop-blur-md border-b border-zinc-800">
        <div className="flex items-center gap-2">
          <div className="p-1 rounded-lg bg-indigo-600 text-white">
            <Smartphone className="w-4 h-4" />
          </div>
          <div>
            <h1 className="text-xs font-bold text-zinc-100">随行任务看板</h1>
            <span className="text-[10px] text-zinc-400 font-mono">
              Session: {activeTask.sessionId.slice(-6)}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-zinc-800/80 border border-zinc-750 text-[10px] font-mono">
          <Radio
            className={`w-3 h-3 ${
              isConnected ? 'text-emerald-400 animate-pulse' : 'text-zinc-500'
            }`}
          />
          <span className={isConnected ? 'text-emerald-300' : 'text-zinc-400'}>
            {isConnected ? '实时同步中' : '未连接'}
          </span>
        </div>
      </header>

      {/* 2. 核心任务进度卡片 */}
      <main className="p-4 space-y-4 flex-1">
        <section className="p-4 rounded-2xl bg-zinc-900/90 border border-zinc-800 shadow-xl space-y-3">
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-sm font-bold text-zinc-100 leading-snug">
              {activeTask.taskName}
            </h2>
            <span
              className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold border shrink-0 ${phaseBadge.badgeClass}`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${phaseBadge.dotClass}`} />
              {phaseBadge.label}
            </span>
          </div>

          {/* 进度条与剩余时间 */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between text-xs">
              <span className="text-zinc-400 font-mono">完成度: {activeTask.progress}%</span>
              <span className="text-indigo-300 font-mono flex items-center gap-1 text-[11px]">
                <Clock className="w-3 h-3 text-indigo-400" />
                剩余: {timeRemainingStr}
              </span>
            </div>

            <div className="w-full bg-zinc-950 rounded-full h-2 overflow-hidden border border-zinc-800">
              <div
                className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-cyan-400 transition-all duration-500 shadow-[0_0_12px_rgba(99,102,241,0.6)]"
                style={{ width: `${activeTask.progress}%` }}
              />
            </div>
          </div>
        </section>

        {/* 3. 沙箱浏览器实时渲染截屏缩略图 (Live Screenshot Preview) */}
        {activeTask.latestScreenshot && (
          <section className="p-3.5 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-2">
            <div className="flex items-center justify-between text-xs">
              <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5 text-cyan-400" />
                沙箱最新网页渲染截屏
              </span>
              <span className="text-[10px] text-zinc-500 font-mono">
                {new Date(activeTask.latestScreenshot.timestamp).toLocaleTimeString()}
              </span>
            </div>

            <div className="relative rounded-xl overflow-hidden border border-zinc-800 bg-zinc-950 aspect-video flex items-center justify-center group">
              {/* oxlint-disable-next-line next/no-img-element -- dynamic screenshot preview from sandbox WebSocket channel */}
              <img
                src={activeTask.latestScreenshot.url}
                alt={activeTask.latestScreenshot.title}
                className="w-full h-full object-cover"
              />
              <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/40 to-transparent p-2 text-[10px] text-zinc-300 font-mono truncate">
                {activeTask.latestScreenshot.title}
              </div>
            </div>
          </section>
        )}

        {/* 4. 高信噪比关键里程碑流 */}
        <section className="p-3.5 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-2">
          <div className="flex items-center justify-between text-xs">
            <span className="font-semibold text-zinc-200 flex items-center gap-1.5">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
              关键执行里程碑 (高信噪比)
            </span>
          </div>

          <div className="space-y-1.5">
            {activeTask.highSnrSummary.map((log, idx) => (
              <div
                key={`snr-${idx}`}
                className="flex items-start gap-2 p-2 rounded-lg bg-zinc-950/60 border border-zinc-850 text-xs text-zinc-300 leading-relaxed font-mono"
              >
                <span className="text-indigo-400 font-bold shrink-0">{idx + 1}.</span>
                <span>{log}</span>
              </div>
            ))}
          </div>
        </section>

        {/* 5. 阶段性产物工件列表 */}
        {activeTask.artifacts.length > 0 && (
          <section className="p-3.5 rounded-2xl bg-zinc-900/90 border border-zinc-800 space-y-2">
            <span className="text-xs font-semibold text-zinc-200 flex items-center gap-1.5">
              <FileCode className="w-3.5 h-3.5 text-indigo-400" />
              已生成工件交付物 ({activeTask.artifacts.length})
            </span>

            <div className="space-y-1.5">
              {activeTask.artifacts.map((art) => (
                <div
                  key={art.id}
                  className="flex items-center justify-between p-2.5 rounded-xl bg-zinc-950/70 border border-zinc-850 hover:border-zinc-750 transition-colors"
                >
                  <div className="flex items-center gap-2 truncate pr-2">
                    {renderArtifactIcon(art.type)}
                    <div className="truncate">
                      <div className="text-xs font-mono text-zinc-200 truncate">{art.name}</div>
                      <div className="text-[10px] text-zinc-500 font-mono">
                        {(art.size / 1024).toFixed(1)} KB
                      </div>
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={() => {
                      handleDownload(art);
                    }}
                    className="p-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors"
                    title={`下载 ${art.name}`}
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </section>
        )}
      </main>

      {/* 6. 底部固定远程遥控与审批条 */}
      <MobileRemoteSteeringBar />
    </div>
  );
};
