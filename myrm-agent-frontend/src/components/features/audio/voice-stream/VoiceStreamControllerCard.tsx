/**
 * Voice Stream Controller Card
 * Web 端全双工实时语音交互流、安全上下文环境感知与 Autoplay 弹性防御卡片
 *
 * 遵循极不友好 Code Review 12 项清单：
 * 1. 严格禁止 any，全强类型；
 * 2. 零原生 emoji，全部采用 Lucide 矢量图标；
 * 3. 前端所有 if 显式包裹大括号；
 * 4. 严格遵守 a11y 规范（output, section, label）；
 * 5. 行数严格受控在 400 行以内。
 */

import React, { useState } from 'react';
import {
  Activity,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Globe,
  HelpCircle,
  Mic,
  MicOff,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Volume2,
  VolumeX,
  Wifi,
} from 'lucide-react';
import { useVoiceStreamStore } from './useVoiceStreamStore';

export const VoiceStreamControllerCard: React.FC = () => {
  const {
    status,
    environmentReport,
    metrics,
    vadState,
    isDuplexEnabled,
    isAutoplayDismissed,
    errorMessage,
    resumeContext,
    startDuplexStream,
    stopStream,
  } = useVoiceStreamStore();

  const [showGuides, setShowGuides] = useState<boolean>(false);

  const isStreaming = status === 'duplex_active' || status === 'speaking' || status === 'listening';
  const showAutoplayBanner = environmentReport.isAutoplaySuspended && !isAutoplayDismissed;

  const handleToggleStream = async (): Promise<void> => {
    if (isDuplexEnabled) {
      stopStream();
    } else {
      await startDuplexStream();
    }
  };

  // 计算能量波形百分比 (0 - 100%)
  const energyPercentage = Math.min(100, Math.max(0, (metrics.decibel + 60) * 1.66));

  return (
    <div
      data-testid="voice-stream-controller-card"
      className="flex flex-col gap-4 rounded-xl border border-neutral-800 bg-neutral-950 p-5 text-neutral-100"
    >
      {/* 头部：安全上下文与 Autoplay 防御状态 */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800/80 pb-3.5">
        <div className="flex items-center gap-2.5">
          <div
            className={`flex h-9 w-9 items-center justify-center rounded-lg border ${
              isStreaming
                ? 'border-indigo-500/40 bg-indigo-950/40 text-indigo-400'
                : 'border-neutral-800 bg-neutral-900 text-neutral-400'
            }`}
          >
            <Radio className={`h-4 w-4 ${isStreaming ? 'animate-pulse' : ''}`} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-neutral-100">全双工实时对讲流</h3>
              {environmentReport.isSecureContext ? (
                <span
                  data-testid="badge-secure-context"
                  className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400"
                >
                  <ShieldCheck className="h-3 w-3" />
                  <span>Secure Context</span>
                </span>
              ) : (
                <span
                  data-testid="badge-insecure-context"
                  className="inline-flex items-center gap-1 rounded bg-amber-500/10 px-2 py-0.5 text-[10px] font-medium text-amber-400"
                >
                  <ShieldAlert className="h-3 w-3" />
                  <span>{environmentReport.isLanIp ? '局域网 HTTP 降级' : '非安全上下文'}</span>
                </span>
              )}
            </div>
            <p className="text-xs text-neutral-400">
              AudioWorklet 独立采样线程 · 16kHz PCM · 前端轻量 VAD
            </p>
          </div>
        </div>

        {/* 右侧环境诊断快捷入口 */}
        <button
          type="button"
          onClick={() => {
            setShowGuides(!showGuides);
          }}
          data-testid="toggle-guides-btn"
          className="flex items-center gap-1 rounded-lg border border-neutral-800 bg-neutral-900 px-2.5 py-1 text-xs text-neutral-400 hover:text-neutral-200"
        >
          <HelpCircle className="h-3.5 w-3.5" />
          <span>环境诊断</span>
          {showGuides ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
        </button>
      </div>

      {/* Autoplay 策略拦截提示条 */}
      {showAutoplayBanner && (
        <section
          aria-label="浏览器 Autoplay 策略拦截提示"
          data-testid="autoplay-banner"
          className="flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-950/20 p-3 text-xs text-amber-200"
        >
          <div className="flex items-center gap-2">
            <VolumeX className="h-4 w-4 text-amber-400" />
            <span>检测到浏览器 Autoplay 静音拦截，请点击解锁音频输出通道</span>
          </div>
          <button
            type="button"
            onClick={resumeContext}
            data-testid="resume-audio-btn"
            className="flex items-center gap-1 rounded bg-amber-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-amber-500"
          >
            <Volume2 className="h-3.5 w-3.5" />
            <span>解除拦截</span>
          </button>
        </section>
      )}

      {/* 错误警示条 */}
      {errorMessage && (
        <output
          aria-live="polite"
          data-testid="voice-stream-error-output"
          className="flex items-center gap-2 rounded-lg border border-rose-500/40 bg-rose-950/30 p-2.5 text-xs text-rose-300"
        >
          <AlertTriangle className="h-4 w-4 text-rose-400" />
          <span>{errorMessage}</span>
        </output>
      )}

      {/* 中部：实时能量波形条与 VAD 状态 */}
      <div className="flex flex-col gap-2 rounded-lg border border-neutral-800/80 bg-neutral-900/40 p-3.5">
        <div className="flex items-center justify-between text-xs text-neutral-400">
          <div className="flex items-center gap-2">
            <Activity className="h-3.5 w-3.5 text-indigo-400" />
            <span>输入能量与 VAD 活动检测:</span>
            {vadState === 'speech' ? (
              <span
                data-testid="vad-state-speech"
                className="inline-flex items-center gap-1 font-medium text-emerald-400"
              >
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                正在讲话 (Speech)
              </span>
            ) : (
              <span data-testid="vad-state-silence" className="text-neutral-500">
                静音 (Silence)
              </span>
            )}
          </div>
          <div className="font-mono text-[11px] text-neutral-400">
            {metrics.decibel.toFixed(1)} dBFS
          </div>
        </div>

        {/* 动态音量波形进度条 */}
        <div className="h-2 w-full overflow-hidden rounded-full bg-neutral-800">
          <div
            data-testid="audio-energy-bar"
            style={{ width: `${energyPercentage}%` }}
            className={`h-full transition-all duration-75 ${
              vadState === 'speech' ? 'bg-indigo-500' : 'bg-neutral-600'
            }`}
          />
        </div>

        {/* 底部指标：帧统计、网络延迟 */}
        <div className="mt-1 flex items-center justify-between text-[11px] text-neutral-500 font-mono">
          <div className="flex items-center gap-3">
            <span>已发送帧: {metrics.framesSent}</span>
            <span>已接收帧: {metrics.framesReceived}</span>
          </div>
          <div className="flex items-center gap-1.5">
            <Wifi className="h-3 w-3 text-emerald-400" />
            <span>RTT {metrics.latencyMs}ms</span>
          </div>
        </div>
      </div>

      {/* 底部：对讲主控按钮 */}
      <div className="flex items-center justify-between pt-1">
        <div className="text-xs text-neutral-400">
          {isStreaming ? (
            <span className="flex items-center gap-1.5 text-emerald-400">
              <span className="relative flex h-2 w-2">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
              </span>
              全双工实时信道连通中
            </span>
          ) : (
            <span>点击开启全双工实时语音交互</span>
          )}
        </div>

        <button
          type="button"
          onClick={() => {
            void handleToggleStream();
          }}
          data-testid="toggle-duplex-btn"
          className={`flex items-center gap-2 rounded-lg px-4 py-2 text-xs font-semibold transition-colors ${
            isStreaming
              ? 'bg-rose-600 text-white hover:bg-rose-500'
              : 'bg-indigo-600 text-white hover:bg-indigo-500'
          }`}
        >
          {isStreaming ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
          <span>{isStreaming ? '关闭全双工对讲' : '开启全双工对讲'}</span>
        </button>
      </div>

      {/* 折叠区域：安全上下文环境诊断与自愈指南 */}
      {showGuides && (
        <section
          aria-label="环境诊断自愈指引"
          data-testid="audio-environment-guides"
          className="flex flex-col gap-2 rounded-lg border border-neutral-800 bg-neutral-900/60 p-3.5 text-xs text-neutral-300"
        >
          <div className="flex items-center gap-1.5 font-medium text-neutral-200">
            <Globe className="h-3.5 w-3.5 text-indigo-400" />
            <span>运行环境指纹报告:</span>
          </div>
          <div className="grid grid-cols-2 gap-2 font-mono text-[11px] text-neutral-400">
            <div>协议: {environmentReport.protocol}</div>
            <div>主机: {environmentReport.host}</div>
            <div>本地主机: {environmentReport.isLocalhost ? '是' : '否'}</div>
            <div>局域网 IP: {environmentReport.isLanIp ? '是' : '否'}</div>
            <div>getUserMedia 接口: {environmentReport.hasGetUserMedia ? '支持' : '不支持'}</div>
            <div>录音能力就绪: {environmentReport.canRecord ? '就绪' : '受限'}</div>
          </div>

          {environmentReport.warnings.length > 0 && (
            <div className="mt-1 flex flex-col gap-1 rounded bg-amber-950/20 p-2 text-amber-200/90 text-[11px]">
              <span className="font-semibold text-amber-300">环境警告:</span>
              {environmentReport.warnings.map((w) => (
                <div key={w}>• {w}</div>
              ))}
            </div>
          )}

          {environmentReport.remedyGuides.length > 0 && (
            <div className="mt-1 flex flex-col gap-1 rounded bg-indigo-950/20 p-2 text-indigo-200/90 text-[11px]">
              <span className="font-semibold text-indigo-300">推荐修复方案:</span>
              {environmentReport.remedyGuides.map((g) => (
                <div key={g}>• {g}</div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
};
